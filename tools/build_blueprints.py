#!/usr/bin/env python3
"""Builds the blueprint YAML files in blueprints/automation/ from one place,
so every character shares the same play, quiet-hours and speaker logic.
Run: python3 tools/build_blueprints.py   (needs PyYAML)"""

import os
import yaml

REPO = "https://github.com/SeriousBug/date-everything-home-assistant"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blueprints", "automation")


class Input(str):
    pass


def _input_repr(dumper, data):
    return dumper.represent_scalar("!input", str(data))


class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


Dumper.add_representer(Input, _input_repr)


def _str_repr(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


Dumper.add_representer(str, _str_repr)


def I(name):
    return Input(name)


# ---------- shared inputs ----------

def speakers_input(desc):
    return {
        "name": "Speakers",
        "description": desc,
        "selector": {"entity": {"filter": {"domain": "media_player"}, "multiple": True}},
    }


def folder_input():
    return {
        "name": "Clip folder",
        "description": "Folder in Media > My media where you uploaded the clips.",
        "default": "date_everything",
        "selector": {"text": {}},
    }


def hours_section():
    return {
        "name": "Quiet hours",
        "icon": "mdi:sleep",
        "collapsed": True,
        "input": {
            "awake_from": {
                "name": "Talk from (weekdays)",
                "default": "09:00:00",
                "selector": {"time": {}},
            },
            "weekend_awake_from": {
                "name": "Talk from (Saturday and Sunday)",
                "default": "11:00:00",
                "selector": {"time": {}},
            },
            "awake_until": {
                "name": "Stop talking at",
                "description": "Can be after midnight, like 03:00.",
                "default": "03:00:00",
                "selector": {"time": {}},
            },
        },
    }


def toggle(name, desc=None, default=True):
    d = {"name": name, "default": default, "selector": {"boolean": {}}}
    if desc:
        d["description"] = desc
    return d


def clips(name, default, desc=None):
    d = {
        "name": name,
        "description": desc or "File names, separated by commas. One is picked at random each time.",
        "default": ", ".join(default),
        "selector": {"text": {"multiline": True}},
    }
    return d


def opt_entity(name, desc, domain, device_class=None):
    f = {"domain": domain}
    if device_class:
        f["device_class"] = device_class
    return {
        "name": name,
        "description": desc,
        "default": "",
        "selector": {"entity": {"filter": f}},
    }


def entity(name, desc, domain, device_class=None):
    d = opt_entity(name, desc, domain, device_class)
    d.pop("default")
    return d


def number(name, default, mn, mx, unit, desc=None, step=1):
    d = {
        "name": name,
        "default": default,
        "selector": {"number": {"min": mn, "max": mx, "step": step, "unit_of_measurement": unit, "mode": "box"}},
    }
    if desc:
        d["description"] = desc
    return d


# ---------- shared templates ----------

AWAKE = (
    "{% set n = now().strftime('%H:%M:%S') %}"
    "{% set s = weekend_awake_from if now().weekday() >= 5 else awake_from %}"
    "{% if s <= awake_until %}{{ s <= n < awake_until }}"
    "{% else %}{{ n >= s or n < awake_until }}{% endif %}"
)

COMMON_VARS = {
    "speakers": I("speakers"),
    "folder": I("folder"),
    "awake_from": I("awake_from"),
    "weekend_awake_from": I("weekend_awake_from"),
    "awake_until": I("awake_until"),
}


def wait_quiet():
    return {
        "wait_template": "{{ speakers | select('is_state', 'playing') | list | count == 0 }}",
        "timeout": {"seconds": 45},
        "continue_on_timeout": True,
    }


def play(pool_var, gate=None, target="speakers"):
    """An `if` block that plays one random clip from the comma list in pool_var,
    only while the house is awake, and waits until the speakers are done."""
    conds = [{"condition": "template", "value_template": AWAKE}]
    if gate:
        conds.insert(0, {"condition": "template", "value_template": "{{ " + gate + " }}"})
    conds.append({
        "condition": "template",
        "value_template": "{{ (%s | default('')).split(',') | map('trim') | reject('eq', '') | list | count > 0 }}" % pool_var,
    })
    return {
        "if": conds,
        "then": [
            wait_quiet() if target == "speakers" else {
                "wait_template": "{{ %s | select('is_state', 'playing') | list | count == 0 }}" % target,
                "timeout": {"seconds": 45},
                "continue_on_timeout": True,
            },
            {"variables": {
                "clip": "{{ %s.split(',') | map('trim') | reject('eq', '') | list | random }}" % pool_var,
            }},
            {
                "action": "media_player.play_media",
                "target": {"entity_id": "{{ %s }}" % target},
                "data": {
                    "media_content_id": "media-source://media_source/local/{{ folder }}/{{ clip }}",
                    "media_content_type": "music",
                },
                "continue_on_error": True,
            },
            {"delay": {"seconds": 2}},
            {
                "wait_template": "{{ %s | select('is_state', 'playing') | list | count == 0 }}" % target,
                "timeout": {"seconds": 60},
                "continue_on_timeout": True,
            },
        ],
    }


def blueprint(file, name, desc, inputs, triggers, actions, mode, extra_vars, trigger_vars=None, max_runs=10):
    bp = {
        "blueprint": {
            "name": name,
            "description": desc,
            "domain": "automation",
            "author": "Ari Barmore-Genc",
            "homeassistant": {"min_version": "2024.10.0"},
            "source_url": f"{REPO}/blob/main/blueprints/automation/{file}",
            "input": inputs,
        },
        "mode": mode,
    }
    if mode in ("queued", "parallel"):
        bp["max"] = max_runs
    bp["max_exceeded"] = "silent"
    if trigger_vars:
        bp["trigger_variables"] = trigger_vars
    bp["triggers"] = triggers
    bp["variables"] = {**COMMON_VARS, **extra_vars}
    bp["actions"] = actions
    return bp


def write(file, bp):
    os.makedirs(OUT, exist_ok=True)
    text = yaml.dump(bp, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=1000)
    with open(os.path.join(OUT, file), "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", file)


def trig(t, id_):
    t = dict(t)
    t["id"] = id_
    return t


def when(id_, *seq, conds=None):
    c = [{"condition": "trigger", "id": id_}] + (conds or [])
    return {"conditions": c, "sequence": list(seq)}


DESC_TAIL = (
    "\n\nThe clips are not included. Make them with the free cutting tool and upload them to "
    "Media > My media > date_everything. Guide: " + REPO
)

# =====================================================================
# Dishy
# =====================================================================

dishy_inputs = {
    "machine": entity("Dishwasher machine state", "SmartThings sensor called \"Machine state\" (run / pause / stop).", "sensor"),
    "job": entity("Dishwasher job state", "SmartThings sensor called \"Job state\" (pre_wash / wash / rinse / drying / finish).", "sensor"),
    "speakers": speakers_input("Where Dishy talks. Pick your kitchen speaker."),
    "options": {
        "name": "Options",
        "icon": "mdi:dishwasher",
        "input": {
            "completion": opt_entity(
                "Completion time (optional)",
                "SmartThings \"Completion time\" sensor. Needed for the door-opening line.",
                "sensor", "timestamp"),
            "door_minutes": number("Door line, minutes before the end", 5, 1, 30, "min",
                                   "Samsung dishwashers pop the door open near the end of drying."),
            "course": opt_entity("Cycle select (optional)", "SmartThings \"Cycle\" select, to skip short cycles.", "select"),
            "skip_courses": {
                "name": "Cycles that stay silent",
                "default": "pre_blast, selfSanitize",
                "selector": {"text": {}},
            },
            "intro_on": toggle("Intro line when a wash starts"),
            "start_on": toggle("Cycle start line"),
            "door_on": toggle("Door opening line (Lime Dawn)"),
            "end_on": toggle("Cycle finished line"),
            "folder": folder_input(),
        },
    },
    "lines": {
        "name": "Voice lines",
        "icon": "mdi:account-voice",
        "collapsed": True,
        "input": {
            "intro_clips": clips("Intro", ["dishy_intro_my_name_is_dishy.mp3"]),
            "start_clips": clips("Cycle start", [
                "dishy_start_basic_info.mp3", "dishy_start_preferred_style.mp3", "dishy_start_unleash_whirlpool.mp3",
                "dishy_start_infinite_domination.mp3", "dishy_start_dish_and_stain.mp3", "dishy_start_hello_welcome.mp3",
                "dishy_start_whirlpool_destruction.mp3", "dishy_start_clean_wash_dry.mp3", "dishy_start_wait_a_moment.mp3"]),
            "door_clips": clips("Door opens to dry", ["dishy_door_lime_dawn.mp3"]),
            "end_clips": clips("Cycle finished", [
                "dishy_end_great_at_dishes.mp3", "dishy_end_great_at_dishes_long.mp3", "dishy_end_well_done_human.mp3",
                "dishy_end_job_well_done.mp3", "dishy_end_cleanest_dishwear.mp3", "dishy_end_clean_as_whistle.mp3",
                "dishy_end_happy_cleansing.mp3", "dishy_end_it_is_done.mp3", "dishy_end_done_together.mp3",
                "dishy_end_youre_welcome.mp3"]),
        },
    },
    "hours": hours_section(),
}

DOOR_READY = (
    "completion != '' and is_state(machine, 'run') "
    "and states(job) not in ['pre_wash', 'unknown', 'unavailable', 'none'] "
    "and as_timestamp(states(completion), 0) > 0 "
    "and (as_timestamp(states(completion), 0) - now().timestamp()) <= door_minutes * 60"
)

dishy = blueprint(
    "dishy.yaml",
    "Date Everything! Dishy (dishwasher voice lines)",
    "Your dishwasher talks like Dishy. Intro and a start line when a real wash starts, "
    "the Lime Dawn line when the door pops open to dry, and a victory line when it finishes. "
    "Powering it on and off, or cancelling a cycle, stays silent. Made for Samsung dishwashers in SmartThings." + DESC_TAIL,
    dishy_inputs,
    [{"trigger": "state", "entity_id": I("machine"), "from": "stop", "to": "run"}],
    [
        {"condition": "template",
         "value_template": "{{ course == '' or states(course) not in (skip_courses.split(',') | map('trim') | list) }}"},
        play("intro_clips", gate="intro_on"),
        {"delay": {"milliseconds": 1500}},
        play("start_clips", gate="start_on"),
        {"alias": "Wait for the door to open, the finish, or a cancel",
         "wait_template": "{{ (" + DOOR_READY + ") or is_state(job, 'finish') or is_state(machine, 'stop') }}",
         "timeout": {"hours": 6}, "continue_on_timeout": False},
        {"if": [{"condition": "template", "value_template": "{{ " + DOOR_READY + " }}"}],
         "then": [
             play("door_clips", gate="door_on"),
             {"wait_template": "{{ is_state(job, 'finish') or is_state(machine, 'stop') }}",
              "timeout": {"hours": 2}, "continue_on_timeout": False},
         ]},
        {"alias": "A stop right at the end still counts as a finish",
         "wait_template": "{{ is_state(job, 'finish') }}",
         "timeout": {"seconds": 30}, "continue_on_timeout": False},
        play("end_clips", gate="end_on"),
    ],
    "single",
    {
        "machine": I("machine"), "job": I("job"), "completion": I("completion"),
        "door_minutes": I("door_minutes"), "course": I("course"), "skip_courses": I("skip_courses"),
        "intro_on": I("intro_on"), "start_on": I("start_on"), "door_on": I("door_on"), "end_on": I("end_on"),
        "intro_clips": I("intro_clips"), "start_clips": I("start_clips"),
        "door_clips": I("door_clips"), "end_clips": I("end_clips"),
    },
)
write("dishy.yaml", dishy)

# =====================================================================
# Washford & Drysdale
# =====================================================================

WASHER_ACTIVE = "states(wm) in ['run', 'pause'] and states(wj) not in ['none', 'finish', 'unknown', 'unavailable', 'delay_wash']"
DRYER_ACTIVE = "states(dm) in ['run', 'pause'] and states(dj) not in ['none', 'finished', 'unknown', 'unavailable']"

laundry_inputs = {
    "washer_machine": entity("Washer machine state", "Washford's SmartThings \"Machine state\" sensor.", "sensor"),
    "washer_job": entity("Washer job state", "Washford's SmartThings \"Job state\" sensor.", "sensor"),
    "dryer_machine": entity("Dryer machine state", "Drysdale's SmartThings \"Machine state\" sensor.", "sensor"),
    "dryer_job": entity("Dryer job state", "Drysdale's SmartThings \"Job state\" sensor.", "sensor"),
    "speakers": speakers_input("Where they talk. Pick speakers near the laundry."),
    "options": {
        "name": "Options",
        "icon": "mdi:washing-machine",
        "input": {
            "soil": opt_entity("Washer soil level (optional)", "Plays the \"heavy\" lines for heavy loads.", "select"),
            "water_temp": opt_entity("Washer water temperature (optional)", "Adds the cold-water line.", "select"),
            "start_on": toggle("Start lines"),
            "stage_on": toggle("Stage lines (wash, spin, cooling, wrinkle care, pause)"),
            "duo_on": toggle("Washford and Drysdale talk to each other"),
            "end_on": toggle("Finished lines"),
            "folder": folder_input(),
        },
    },
    "washford": {
        "name": "Washford's lines",
        "icon": "mdi:account-voice",
        "collapsed": True,
        "input": {
            "w_start": clips("Start", [
                "washford_start_obtained_a_stain.mp3", "washford_start_wash_away_your_cares.mp3",
                "washford_start_to_wash_to_bathe.mp3", "washford_start_deep_water.mp3",
                "washford_start_dirty_laundry.mp3", "washford_start_weary_traveler.mp3",
                "washford_start_you_are_returned.mp3", "washford_start_weight_on_my_drum.mp3"]),
            "w_heavy": clips("Heavy load start", ["washford_heavy_dirt_of_life.mp3", "washford_heavy_absolved.mp3"]),
            "w_cold": clips("Cold water (after the start line)", ["washford_cold_without_heat.mp3"]),
            "w_delay": clips("Delayed start", ["washford_delay_wait_until_you_return.mp3", "washford_delay_readiness.mp3"]),
            "w_wash": clips("Washing", ["washford_wash_filled_with_water.mp3", "washford_wash_drop_of_water.mp3"]),
            "w_spin": clips("Spinning", ["washford_spin_whoosh.mp3", "washford_spin_swift_smooth_strong.mp3",
                                           "washford_spin_we_would_fly.mp3"]),
            "w_pause": clips("Paused", ["washford_pause_patience.mp3"]),
            "w_end": clips("Finished", [
                "washford_end_moving_things.mp3", "washford_end_spinning_cycles.mp3", "washford_end_walk_cleanly.mp3",
                "washford_end_talk_to_drysdale.mp3", "washford_end_hurry_back.mp3", "washford_end_farewell_friend.mp3"]),
        },
    },
    "drysdale": {
        "name": "Drysdale's lines",
        "icon": "mdi:account-voice",
        "collapsed": True,
        "input": {
            "d_start": clips("Start", [
                "drysdale_start_cherub_returned.mp3", "drysdale_start_dont_bore_me.mp3", "drysdale_start_vibrating.mp3",
                "drysdale_start_giddy_up.mp3", "drysdale_start_buckle_up.mp3", "drysdale_start_away_we_go.mp3",
                "drysdale_start_magnificent.mp3", "drysdale_start_tremendous_heat.mp3", "drysdale_start_heat_somewhere.mp3"]),
            "d_cool": clips("Cooling down", ["drysdale_cool_heat_of_moment.mp3"]),
            "d_wrinkle": clips("Wrinkle care", ["drysdale_wrinkle_twist_turn.mp3"]),
            "d_pause": clips("Paused / door opened", ["drysdale_pause_drying_out.mp3"]),
            "d_end": clips("Finished", [
                "drysdale_end_clothing_clings.mp3", "drysdale_end_garments_intimately.mp3", "drysdale_end_better_shape.mp3",
                "drysdale_end_points_all_around.mp3", "drysdale_end_bring_chardonnay.mp3", "drysdale_end_generosity.mp3",
                "drysdale_end_dryer_sheets.mp3", "drysdale_end_love_washford.mp3"]),
        },
    },
    "duo": {
        "name": "Duo lines",
        "icon": "mdi:account-multiple",
        "collapsed": True,
        "input": {
            "duo_handoff": clips("Wet clothes go from Washford to Drysdale",
                                 ["duo_handoff_come_drysdale.mp3", "duo_handoff_cheeky_monkey.mp3"]),
            "duo_both": clips("Both running at once",
                              ["duo_both_funny_little_pair.mp3", "duo_both_flirt_and_poet.mp3"]),
        },
    },
    "hours": hours_section(),
}

laundry = blueprint(
    "washford_drysdale.yaml",
    "Date Everything! Washford & Drysdale (washer and dryer voice lines)",
    "Your washer and dryer talk like Washford and Drysdale: start lines (heavy loads, cold water and "
    "delayed starts get their own), lines during the cycle, finished lines, and the two of them talking "
    "to each other when the wet clothes move to the dryer or both run at once. Made for Samsung washers "
    "and dryers in SmartThings." + DESC_TAIL,
    laundry_inputs,
    [
        trig({"trigger": "state", "entity_id": I("washer_machine"), "from": "stop", "to": "run"}, "washer_run"),
        trig({"trigger": "state", "entity_id": I("washer_job"), "from": "delay_wash",
              "not_to": ["none", "unknown", "unavailable", "delay_wash"]}, "washer_run"),
        trig({"trigger": "state", "entity_id": I("washer_job"), "to": ["wash", "ai_wash"]}, "washer_wash"),
        trig({"trigger": "state", "entity_id": I("washer_job"), "to": ["spin", "ai_spin"]}, "washer_spin"),
        trig({"trigger": "state", "entity_id": I("washer_machine"), "from": "run", "to": "pause"}, "washer_pause"),
        trig({"trigger": "state", "entity_id": I("washer_job"), "to": "finish"}, "washer_end"),
        trig({"trigger": "state", "entity_id": I("dryer_machine"), "from": "stop", "to": "run"}, "dryer_run"),
        trig({"trigger": "state", "entity_id": I("dryer_job"), "to": "cooling"}, "dryer_cool"),
        trig({"trigger": "state", "entity_id": I("dryer_job"), "to": "wrinkle_prevent"}, "dryer_wrinkle"),
        trig({"trigger": "state", "entity_id": I("dryer_machine"), "from": "run", "to": "pause"}, "dryer_pause"),
        trig({"trigger": "state", "entity_id": I("dryer_job"), "to": "finished"}, "dryer_end"),
    ],
    [{"choose": [
        when("washer_run",
             {"delay": {"seconds": 20}},
             {"alias": "Only a real cycle (powering on with no cycle stays silent)",
              "condition": "template",
              "value_template": "{{ states(wj) not in ['none', 'finish', 'unknown', 'unavailable'] }}"},
             {"condition": "template", "value_template": "{{ start_on }}"},
             {"choose": [
                 {"conditions": [{"condition": "template", "value_template": "{{ is_state(wj, 'delay_wash') }}"}],
                  "sequence": [play("w_delay")]},
                 {"conditions": [{"condition": "template", "value_template": "{{ duo_on and " + DRYER_ACTIVE + " }}"}],
                  "sequence": [play("duo_both")]},
                 {"conditions": [{"condition": "template",
                                  "value_template": "{{ soil != '' and states(soil) in ['heavy', 'extra_heavy'] }}"}],
                  "sequence": [play("w_heavy")]},
             ], "default": [
                 play("w_start"),
                 play("w_cold", gate="water_temp != '' and states(water_temp) in ['cold', 'cool', 'tap_cold']"),
             ]}),
        when("washer_wash", play("w_wash", gate="stage_on")),
        when("washer_spin", play("w_spin", gate="stage_on")),
        when("washer_pause", play("w_pause", gate="stage_on")),
        when("washer_end", play("w_end", gate="end_on")),
        when("dryer_run",
             {"delay": {"seconds": 10}},
             {"alias": "Only a real drying cycle", "condition": "template",
              "value_template": "{{ states(dj) not in ['none', 'finished', 'unknown', 'unavailable'] }}"},
             {"condition": "template", "value_template": "{{ start_on }}"},
             {"choose": [
                 {"conditions": [{"condition": "template", "value_template":
                                  "{{ duo_on and not (" + WASHER_ACTIVE + ") and states[wm] is not none "
                                  "and (now() - states[wm].last_changed).total_seconds() < 5400 }}"}],
                  "sequence": [play("duo_handoff")]},
                 {"conditions": [{"condition": "template", "value_template": "{{ duo_on and " + WASHER_ACTIVE + " }}"}],
                  "sequence": [play("duo_both")]},
             ], "default": [play("d_start")]}),
        when("dryer_cool", play("d_cool", gate="stage_on")),
        when("dryer_wrinkle", play("d_wrinkle", gate="stage_on")),
        when("dryer_pause", play("d_pause", gate="stage_on")),
        when("dryer_end", play("d_end", gate="end_on")),
    ]}],
    "queued",
    {
        "wm": I("washer_machine"), "wj": I("washer_job"), "dm": I("dryer_machine"), "dj": I("dryer_job"),
        "soil": I("soil"), "water_temp": I("water_temp"),
        "start_on": I("start_on"), "stage_on": I("stage_on"), "duo_on": I("duo_on"), "end_on": I("end_on"),
        "w_start": I("w_start"), "w_heavy": I("w_heavy"), "w_cold": I("w_cold"), "w_delay": I("w_delay"),
        "w_wash": I("w_wash"), "w_spin": I("w_spin"), "w_pause": I("w_pause"), "w_end": I("w_end"),
        "d_start": I("d_start"), "d_cool": I("d_cool"), "d_wrinkle": I("d_wrinkle"), "d_pause": I("d_pause"),
        "d_end": I("d_end"), "duo_handoff": I("duo_handoff"), "duo_both": I("duo_both"),
    },
)
write("washford_drysdale.yaml", laundry)

# =====================================================================
# Hector
# =====================================================================

AIR_BAD = ("(aq != '' and states(aq) | float(0) >= aq_level) or "
           "(pm != '' and states(pm) in ['unhealthy', 'very_unhealthy', 'hazardous'])")
AIR_CLEAR = ("(aq == '' or states(aq) | float(9) <= 2) and "
             "(pm == '' or states(pm) in ['good', 'moderate']) and (aq != '' or pm != '')")

hector_inputs = {
    "fan": entity("Range hood fan", "Hector's fan entity.", "fan"),
    "speakers": speakers_input("Where Hector talks. Pick your kitchen speaker."),
    "options": {
        "name": "Options",
        "icon": "mdi:fan",
        "input": {
            "air_quality": opt_entity("Air quality index sensor (optional)",
                                      "SmartThings \"Air quality\" sensor (1 = good, 4 = bad).", "sensor"),
            "aq_level": number("Smoky at this air quality index or higher", 3, 1, 4, "", step=1),
            "pm25_concern": opt_entity("PM2.5 health concern sensor (optional)",
                                       "Reacts faster than the air quality index while you cook.", "sensor"),
            "filter_usage": opt_entity("Filter usage sensor (optional)", "Percent of filter life used.", "sensor"),
            "filter_alert_at": number("Remind about the filter at", 100, 50, 100, "%"),
            "filter_button": opt_entity("Filter reset button (optional)", "Pressing it plays a thank-you line.", "button"),
            "long_minutes": number("\"Still running\" line after", 90, 15, 480, "min"),
            "onoff_on": toggle("Fan on and off lines"),
            "air_on": toggle("Smoky air lines"),
            "filter_on": toggle("Filter lines"),
            "long_on": toggle("Still running line"),
            "folder": folder_input(),
        },
    },
    "lines": {
        "name": "Voice lines",
        "icon": "mdi:account-voice",
        "collapsed": True,
        "input": {
            "on_clips": clips("Fan turns on", [
                "hector_on_at_your_service.mp3", "hector_on_here_you_are.mp3", "hector_on_hello_again.mp3",
                "hector_on_rush_of_air.mp3", "hector_on_you_returned.mp3", "hector_on_whatever_you_need.mp3",
                "hector_on_serve_you.mp3", "hector_on_welcome_to_stop_by.mp3", "hector_on_breathing_freedom.mp3"]),
            "off_clips": clips("Fan turns off", [
                "hector_off_come_back_any_time.mp3", "hector_off_whenever_ready.mp3", "hector_off_through_the_grates.mp3",
                "hector_off_always_here.mp3", "hector_off_speak_again_soon.mp3", "hector_off_goodbye_now.mp3",
                "hector_off_rest_in_contentment.mp3", "hector_off_take_your_time.mp3"]),
            "air_clips": clips("Smoky air, fan running", [
                "hector_air_storm_brewing.mp3", "hector_air_play_of_air.mp3", "hector_air_so_much_energy.mp3",
                "hector_air_intensity.mp3"]),
            "nudge_clips": clips("Smoky air, fan off (turn me on!)", [
                "hector_nudge_doesnt_sound_good.mp3", "hector_nudge_let_me_care.mp3", "hector_nudge_need_to_care.mp3",
                "hector_nudge_how_can_i_help.mp3", "hector_nudge_worst_fear.mp3"]),
            "clear_clips": clips("Air cleared", [
                "hector_clear_light_and_space.mp3", "hector_on_breathing_freedom.mp3", "hector_off_rest_in_contentment.mp3"]),
            "filter_clips": clips("Filter is full", ["hector_filter_full_of_dust.mp3", "hector_filter_simple_matter.mp3"]),
            "filter_done_clips": clips("Filter cleaned", [
                "hector_filter_thanks_fresh_filter.mp3", "hector_filter_tired_filter.mp3",
                "hector_filter_conscientious.mp3", "hector_filter_have_filters_for_that.mp3"]),
            "long_clips": clips("Still running", ["hector_long_wait_here.mp3", "hector_long_buttons_dials.mp3"]),
        },
    },
    "hours": hours_section(),
}

hector = blueprint(
    "hector.yaml",
    "Date Everything! Hector (range hood voice lines)",
    "Your range hood talks like Hector: lines when the fan turns on and off, when the kitchen gets smoky "
    "(and a nudge to turn him on if he's off), when the air clears, when the filter is full and when it "
    "gets cleaned. Made for Samsung range hoods in SmartThings, but any fan works for the on/off lines." + DESC_TAIL,
    hector_inputs,
    [
        trig({"trigger": "state", "entity_id": I("fan"), "from": "off", "to": "on"}, "fan_on"),
        trig({"trigger": "state", "entity_id": I("fan"), "from": "on", "to": "off"}, "fan_off"),
        trig({"trigger": "state", "entity_id": I("fan"), "to": "on", "for": {"minutes": I("long_minutes")}}, "long"),
        trig({"trigger": "template", "value_template": "{{ " + AIR_BAD + " }}", "for": {"minutes": 1}}, "air_bad"),
        trig({"trigger": "template",
              "value_template": "{{ fu != '' and states(fu) | float(0) >= filter_alert_at }}"}, "filter_full"),
        trig({"trigger": "template",
              "value_template": "{{ fu != '' and states(fu) not in ['unknown', 'unavailable'] and states(fu) | float(100) < 10 }}"},
             "filter_reset"),
        trig({"trigger": "event", "event_type": "state_changed",
              "event_data": {"entity_id": I("filter_button")}}, "button"),
    ],
    [{"choose": [
        when("fan_on", play("on_clips", gate="onoff_on")),
        when("fan_off", play("off_clips", gate="onoff_on"),
             conds=[{"alias": "Ran at least a minute", "condition": "template",
                     "value_template": "{{ (now() - trigger.from_state.last_changed).total_seconds() >= 60 }}"}]),
        when("long", play("long_clips", gate="long_on")),
        when("air_bad",
             {"condition": "template", "value_template": "{{ air_on }}"},
             {"if": [{"condition": "state", "entity_id": I("fan"), "state": "on"}],
              "then": [play("air_clips")], "else": [play("nudge_clips")]},
             {"alias": "Wait for the air to clear",
              "wait_for_trigger": [{"trigger": "template", "value_template": "{{ " + AIR_CLEAR + " }}",
                                    "for": {"minutes": 10}}],
              "timeout": {"hours": 4}, "continue_on_timeout": False},
             play("clear_clips")),
        when("filter_full",
             {"condition": "template", "value_template": "{{ filter_on }}"},
             {"alias": "Say it the next time the fan turns on",
              "wait_for_trigger": [{"trigger": "state", "entity_id": I("fan"), "from": "off", "to": "on"}],
              "timeout": {"days": 14}, "continue_on_timeout": False},
             {"delay": {"seconds": 6}},
             play("filter_clips")),
        when("filter_reset", play("filter_done_clips", gate="filter_on")),
        when("button", play("filter_done_clips", gate="filter_on"),
             conds=[{"condition": "template",
                     "value_template": "{{ trigger.event.data.old_state is not none and trigger.event.data.new_state is not none "
                                       "and trigger.event.data.old_state.state not in ['unavailable'] "
                                       "and trigger.event.data.new_state.state not in ['unavailable', 'unknown'] "
                                       "and trigger.event.data.old_state.state != trigger.event.data.new_state.state }}"}]),
    ]}],
    "parallel",
    {
        "fan": I("fan"), "air_on": I("air_on"), "onoff_on": I("onoff_on"), "filter_on": I("filter_on"),
        "long_on": I("long_on"),
        "on_clips": I("on_clips"), "off_clips": I("off_clips"), "air_clips": I("air_clips"),
        "nudge_clips": I("nudge_clips"), "clear_clips": I("clear_clips"), "filter_clips": I("filter_clips"),
        "filter_done_clips": I("filter_done_clips"), "long_clips": I("long_clips"),
    },
    trigger_vars={"aq": I("air_quality"), "aq_level": I("aq_level"), "pm": I("pm25_concern"),
                  "fu": I("filter_usage"), "filter_alert_at": I("filter_alert_at")},
)
# AIR_CLEAR inside the wait needs the same names as normal variables
hector["variables"].update({"aq": I("air_quality"), "pm": I("pm25_concern")})
write("hector.yaml", hector)

# =====================================================================
# Airyn
# =====================================================================

NOT_ECO = "not (skip_eco and state_attr(thermostat, 'preset_mode') == 'eco')"

airyn_inputs = {
    "thermostat": entity("Thermostat", "Airyn's climate entity.", "climate"),
    "speakers": speakers_input("Where Airyn talks. One room is plenty, she's dramatic."),
    "options": {
        "name": "Options",
        "icon": "mdi:thermostat",
        "input": {
            "mode_on": toggle("Heat / cool switch lines"),
            "humidity_on": toggle("Too dry / too humid lines"),
            "dry_below": number("Too dry below", 30, 10, 50, "%"),
            "humid_above": number("Too humid above", 60, 40, 90, "%"),
            "offline_on": toggle("Offline and back online lines"),
            "skip_eco": toggle("Stay quiet while in Eco mode", "Eco usually means nobody's home."),
            "filter_on": toggle("Filter reminders"),
            "filter_date": opt_entity(
                "Filter last changed (optional)",
                "A Date helper you create (Settings > Devices & services > Helpers > Date and/or time). "
                "Needed for filter reminders.", "input_datetime"),
            "filter_days": number("Change the filter every", 90, 14, 365, "days"),
            "filter_repeat": number("Remind again every", 7, 1, 30, "days"),
            "filter_time": {"name": "Filter reminder time", "default": "19:00:00", "selector": {"time": {}}},
            "filter_button": opt_entity(
                "\"Filter replaced\" button (optional)",
                "A Button helper. Press it after a new filter: it resets the date and Airyn thanks you.",
                "input_button"),
            "folder": folder_input(),
        },
    },
    "lines": {
        "name": "Voice lines",
        "icon": "mdi:account-voice",
        "collapsed": True,
        "input": {
            "heat_clips": clips("Switched to heat", ["airyn_heat_making_me_cold.mp3", "airyn_mode_i_am_airyn.mp3",
                                                     "airyn_mode_breathe_me.mp3"]),
            "cool_clips": clips("Switched to cool", ["airyn_mode_shift_with_wind.mp3", "airyn_mode_i_am_airyn.mp3"]),
            "change_clips": clips("Switched to heat + cool", ["airyn_mode_i_am_airyn.mp3", "airyn_mode_breathe_me.mp3",
                                                              "airyn_mode_shift_with_wind.mp3"]),
            "air_clips": clips("Too dry or too humid", ["airyn_air_breathe_child.mp3", "airyn_air_always_listening.mp3",
                                                        "airyn_air_admixture.mp3"]),
            "offline_clips": clips("Offline", ["airyn_offline_gasping.mp3"]),
            "online_clips": clips("Back online", ["airyn_online_accompany.mp3", "airyn_online_you_return.mp3"]),
            "filter_clips": clips("Filter is due", [
                "airyn_filter_not_nearly_enough.mp3", "airyn_filter_instill_panic.mp3", "airyn_filter_tire_of_this.mp3",
                "airyn_filter_leave_me_be.mp3", "airyn_filter_grow_weary.mp3"]),
            "filter_done_clips": clips("Filter replaced", [
                "airyn_filter_done_make_me_anew.mp3", "airyn_filter_done_well_done.mp3",
                "airyn_filter_done_quite_impressed.mp3", "airyn_filter_done_pleasure.mp3"]),
        },
    },
    "hours": hours_section(),
}

FILTER_DUE = (
    "filter_date != '' and states(filter_date) not in ['unknown', 'unavailable', ''] "
    "and ((now().date() - (states(filter_date) | as_datetime).date()).days - filter_days) >= 0 "
    "and ((now().date() - (states(filter_date) | as_datetime).date()).days - filter_days) % filter_repeat == 0"
)

airyn = blueprint(
    "airyn.yaml",
    "Date Everything! Airyn (thermostat voice lines)",
    "Your thermostat talks like Airyn, kept quiet on purpose: lines when it switches between heating and "
    "cooling, when the air gets too dry or humid, when it drops offline and comes back, and filter "
    "reminders. Nothing for normal heating and cooling runs. Works with any thermostat in Home Assistant "
    "(made with a Google Nest)." + DESC_TAIL,
    airyn_inputs,
    [
        trig({"trigger": "state", "entity_id": I("thermostat"), "to": None,
              "not_from": ["unavailable", "unknown"]}, "mode"),
        trig({"trigger": "state", "entity_id": I("thermostat"), "to": "unavailable", "for": {"minutes": 10}}, "offline"),
        trig({"trigger": "numeric_state", "entity_id": I("thermostat"), "attribute": "current_humidity",
              "below": I("dry_below"), "for": {"minutes": 30}}, "air"),
        trig({"trigger": "numeric_state", "entity_id": I("thermostat"), "attribute": "current_humidity",
              "above": I("humid_above"), "for": {"minutes": 30}}, "air"),
        trig({"trigger": "time", "at": I("filter_time")}, "filter_check"),
        trig({"trigger": "event", "event_type": "state_changed",
              "event_data": {"entity_id": I("filter_button")}}, "filter_reset"),
    ],
    [{"choose": [
        when("mode",
             {"variables": {"pool": "{{ heat_clips if trigger.to_state.state == 'heat' else "
                                    "(cool_clips if trigger.to_state.state == 'cool' else change_clips) }}"}},
             play("pool", gate="mode_on and " + NOT_ECO),
             conds=[{"condition": "template", "value_template":
                     "{{ trigger.from_state.state in ['heat', 'cool', 'heat_cool'] and "
                     "trigger.to_state.state in ['heat', 'cool', 'heat_cool'] }}"}]),
        when("offline",
             play("offline_clips", gate="offline_on"),
             {"wait_for_trigger": [{"trigger": "state", "entity_id": I("thermostat"), "from": "unavailable"}],
              "timeout": {"days": 7}, "continue_on_timeout": False},
             play("online_clips", gate="offline_on and " + NOT_ECO)),
        when("air", play("air_clips", gate="humidity_on and " + NOT_ECO)),
        when("filter_check", play("filter_clips", gate="filter_on and " + NOT_ECO + " and " + FILTER_DUE)),
        when("filter_reset",
             {"if": [{"condition": "template", "value_template": "{{ filter_date != '' }}"}],
              "then": [{"action": "input_datetime.set_datetime", "target": {"entity_id": "{{ filter_date }}"},
                        "data": {"date": "{{ now().date() | string }}"}}]},
             play("filter_done_clips", gate="filter_on"),
             conds=[{"condition": "template",
                     "value_template": "{{ trigger.event.data.old_state is not none and trigger.event.data.new_state is not none "
                                       "and trigger.event.data.old_state.state not in ['unavailable'] "
                                       "and trigger.event.data.new_state.state not in ['unavailable', 'unknown'] "
                                       "and trigger.event.data.old_state.state != trigger.event.data.new_state.state }}"}]),
    ]}],
    "parallel",
    {
        "thermostat": I("thermostat"), "mode_on": I("mode_on"), "humidity_on": I("humidity_on"),
        "offline_on": I("offline_on"), "skip_eco": I("skip_eco"), "filter_on": I("filter_on"),
        "filter_date": I("filter_date"), "filter_days": I("filter_days"), "filter_repeat": I("filter_repeat"),
        "heat_clips": I("heat_clips"), "cool_clips": I("cool_clips"), "change_clips": I("change_clips"),
        "air_clips": I("air_clips"), "offline_clips": I("offline_clips"), "online_clips": I("online_clips"),
        "filter_clips": I("filter_clips"), "filter_done_clips": I("filter_done_clips"),
    },
)
write("airyn.yaml", airyn)

# =====================================================================
# Lux
# =====================================================================

lux_inputs = {
    "lights": {
        "name": "Lights",
        "description": "Lights (or light switches) Lux comments on.",
        "selector": {"entity": {"filter": [{"domain": "light"}, {"domain": "switch"}], "multiple": True}},
    },
    "speakers": speakers_input(
        "Lux talks on the speaker in the same room as the light: same area, or the room name in the speaker's name (\"Living Room speaker\"). Rooms without one use the fallback below, or stay quiet."),
    "options": {
        "name": "Options",
        "icon": "mdi:ring-light",
        "input": {
            "fallback_speakers": {
                "name": "Speaker for lights in rooms without a speaker (optional)",
                "default": [],
                "selector": {"entity": {"filter": {"domain": "media_player"}, "multiple": True}},
            },
            "who": {
                "name": "Who makes Lux talk",
                "description": "Wall switches are always ignored by the first two choices.",
                "default": "voice",
                "selector": {"select": {"mode": "list", "options": [
                    {"value": "voice", "label": "Only voice commands (needs the user ID below)"},
                    {"value": "people", "label": "Voice, the app and automations (not wall switches)"},
                    {"value": "everything", "label": "Everything, wall switches included"},
                ]}},
            },
            "voice_user": {
                "name": "Voice assistant user ID",
                "description": "For Google Assistant or Alexa through Home Assistant Cloud: Settings > People > Users "
                               "(turn on Advanced mode in your profile), open \"Home Assistant Cloud\" and copy its ID.",
                "default": "",
                "selector": {"text": {}},
            },
            "onoff_on": toggle("On and off lines"),
            "bright_on": toggle("Brighter and dimmer lines"),
            "offline_on": toggle("Offline lines", "When a light can't be reached for a while."),
            "offline_minutes": number("Offline line after", 60, 10, 720, "min"),
            "cooldown": number("Seconds between lines", 20, 0, 300, "s",
                               "\"Turn off everything\" shouldn't get 12 lines in a row."),
            "folder": folder_input(),
        },
    },
    "lines": {
        "name": "Voice lines",
        "icon": "mdi:account-voice",
        "collapsed": True,
        "input": {
            "on_clips": clips("Light turned on", [
                "lux_on_better_lighting.mp3", "lux_on_brightest_example.mp3", "lux_on_hi_luxies.mp3",
                "lux_on_inner_light.mp3", "lux_on_its_about_lights.mp3", "lux_on_its_me_again.mp3",
                "lux_on_let_your_light_shine.mp3", "lux_on_light_shine_out.mp3", "lux_on_light_up_lives.mp3",
                "lux_on_luminescence.mp3", "lux_on_more_beautiful.mp3", "lux_on_on_all_the_time.mp3",
                "lux_on_shine_bright.mp3", "lux_on_shine_on_luxie.mp3", "lux_on_speed_of_light.mp3",
                "lux_on_that_essential.mp3", "lux_on_whats_up.mp3", "lux_on_you_again.mp3"]),
            "off_clips": clips("Light turned off", [
                "lux_off_bored_with_you.mp3", "lux_off_come_see_me.mp3", "lux_off_dimmer_switch.mp3",
                "lux_off_dimmy_move.mp3", "lux_off_go_to_sleep.mp3", "lux_off_in_charge.mp3", "lux_off_next_date.mp3",
                "lux_off_on_again_off_again.mp3", "lux_off_see_you_around.mp3", "lux_off_six_parties.mp3",
                "lux_off_stay_golden.mp3", "lux_off_switch_yourself_off.mp3", "lux_off_total_disregard.mp3"]),
            "brighter_clips": clips("Made brighter", [
                "lux_on_better_lighting.mp3", "lux_on_brightest_example.mp3", "lux_on_light_shine_out.mp3",
                "lux_on_shine_bright.mp3", "lux_on_inner_light.mp3", "lux_on_more_beautiful.mp3"]),
            "dimmer_clips": clips("Made dimmer", [
                "lux_off_dimmer_switch.mp3", "lux_off_dimmy_move.mp3", "lux_off_total_disregard.mp3",
                "lux_off_go_to_sleep.mp3", "lux_offline_badly_treated.mp3"]),
            "offline_clips": clips("Light offline", [
                "lux_offline_almost_dead.mp3", "lux_offline_badly_treated.mp3", "lux_offline_wifi_sucks.mp3",
                "lux_offline_wish_i_could_help.mp3"]),
        },
    },
    "hours": hours_section(),
}

LUX_SPK = (
    "{% set a = area_id(trigger.entity_id) %}"
    "{% set ns = namespace(here=[]) %}"
    "{% if a %}{% set an = (area_name(a) or '') | lower %}"
    "{% for s in speakers %}"
    "{% if area_id(s) == a or (an != '' and an in (state_attr(s, 'friendly_name') or s) | lower) %}"
    "{% set ns.here = ns.here + [s] %}{% endif %}"
    "{% endfor %}{% endif %}"
    "{{ ns.here if ns.here else fallback_speakers }}"
)
LUX_WHO = (
    "{% set c = trigger.to_state.context %}"
    "{% if who == 'everything' %}true"
    "{% elif who == 'voice' %}{{ voice_user != '' and c.user_id == voice_user }}"
    "{% else %}{{ c.user_id is not none or c.parent_id is not none }}{% endif %}"
)

lux = blueprint(
    "lux.yaml",
    "Date Everything! Lux (light voice lines)",
    "Lux, the ring light influencer, comments when your lights turn on, off, brighter or dimmer, and "
    "complains when one has been offline for too long. They talk on the speaker in the light's room. "
    "By default only voice commands set them off, so flipping a wall switch stays quiet." + DESC_TAIL,
    lux_inputs,
    [
        trig({"trigger": "state", "entity_id": I("lights"), "from": ["on", "off"], "to": ["on", "off"]}, "change"),
        trig({"trigger": "state", "entity_id": I("lights"), "attribute": "brightness"}, "bright"),
        trig({"trigger": "state", "entity_id": I("lights"), "to": "unavailable",
              "for": {"minutes": I("offline_minutes")}}, "offline"),
    ],
    [
        {"variables": {"spk": LUX_SPK}},
        {"condition": "template", "value_template": "{{ spk | count > 0 }}"},
        {"choose": [
            when("change",
                 {"variables": {"pool": "{{ on_clips if trigger.to_state.state == 'on' else off_clips }}"}},
                 play("pool", gate="onoff_on", target="spk"),
                 conds=[{"condition": "template", "value_template": LUX_WHO}]),
            when("bright",
                 {"variables": {"pool": "{{ brighter_clips if trigger.to_state.attributes.brightness > "
                                        "trigger.from_state.attributes.brightness else dimmer_clips }}"}},
                 play("pool", gate="bright_on", target="spk"),
                 conds=[
                     {"condition": "template", "value_template":
                      "{{ trigger.from_state.state == 'on' and trigger.to_state.state == 'on' "
                      "and trigger.from_state.attributes.brightness is number "
                      "and trigger.to_state.attributes.brightness is number "
                      "and (trigger.to_state.attributes.brightness - trigger.from_state.attributes.brightness) | abs >= 13 }}"},
                     {"condition": "template", "value_template": LUX_WHO},
                 ]),
            when("offline", play("offline_clips", gate="offline_on", target="spk")),
        ]},
        {"delay": {"seconds": I("cooldown")}},
    ],
    "single",
    {
        "fallback_speakers": I("fallback_speakers"), "who": I("who"), "voice_user": I("voice_user"),
        "onoff_on": I("onoff_on"), "bright_on": I("bright_on"), "offline_on": I("offline_on"),
        "on_clips": I("on_clips"), "off_clips": I("off_clips"), "brighter_clips": I("brighter_clips"),
        "dimmer_clips": I("dimmer_clips"), "offline_clips": I("offline_clips"),
    },
)
write("lux.yaml", lux)
