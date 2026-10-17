"""Render an SVG to PNG with the system librsvg + cairo through ctypes.
Usage: python3 svg2png.py in.svg out.png WIDTH HEIGHT"""
import ctypes, sys

rsvg = ctypes.CDLL("librsvg-2.so.2")
cairo = ctypes.CDLL("libcairo.so.2")
gobj = ctypes.CDLL("libgobject-2.0.so.0")

src, dst, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])

rsvg.rsvg_handle_new_from_file.restype = ctypes.c_void_p
rsvg.rsvg_handle_new_from_file.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
err = ctypes.c_void_p()
handle = rsvg.rsvg_handle_new_from_file(src.encode(), ctypes.byref(err))
if not handle:
    raise SystemExit("could not load svg")


class Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double),
                ("width", ctypes.c_double), ("height", ctypes.c_double)]


cairo.cairo_image_surface_create.restype = ctypes.c_void_p
cairo.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
cairo.cairo_create.restype = ctypes.c_void_p
cairo.cairo_create.argtypes = [ctypes.c_void_p]
cairo.cairo_surface_write_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
cairo.cairo_destroy.argtypes = [ctypes.c_void_p]
cairo.cairo_surface_destroy.argtypes = [ctypes.c_void_p]

surface = cairo.cairo_image_surface_create(0, w, h)  # CAIRO_FORMAT_ARGB32
cr = cairo.cairo_create(surface)
rsvg.rsvg_handle_render_document.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(Rect), ctypes.c_void_p]
rsvg.rsvg_handle_render_document.restype = ctypes.c_int
ok = rsvg.rsvg_handle_render_document(handle, cr, ctypes.byref(Rect(0, 0, w, h)), ctypes.byref(err))
if not ok:
    raise SystemExit("render failed")
cairo.cairo_surface_write_to_png(surface, dst.encode())
cairo.cairo_destroy(cr)
cairo.cairo_surface_destroy(surface)
gobj.g_object_unref.argtypes = [ctypes.c_void_p]
gobj.g_object_unref(handle)
print("wrote", dst)
