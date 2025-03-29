# encoding: utf-8
import os
import re
from contextlib import contextmanager, ExitStack
from ..lib.cocoa import *

from plotdevice import DeviceError
from ..util import _copy_attr, _copy_attrs, numlike
from .colors import Color
from .geometry import Point
from . import _cg_context, _cg_layer, _cg_port

_ctx = None
__all__ = ("Effect", "Shadow", "Stencil", "Raster")

# Blend modes organized by category
_BLEND = {
    # Basic blend modes
    'normal': kCGBlendModeNormal,
    'clear': kCGBlendModeClear,
    'copy': kCGBlendModeCopy,

    # Standard blend modes
    'multiply': kCGBlendModeMultiply,
    'screen': kCGBlendModeScreen,
    'overlay': kCGBlendModeOverlay,
    'darken': kCGBlendModeDarken,
    'lighten': kCGBlendModeLighten,
    'colordodge': kCGBlendModeColorDodge,
    'colorburn': kCGBlendModeColorBurn,
    'softlight': kCGBlendModeSoftLight,
    'hardlight': kCGBlendModeHardLight,
    'difference': kCGBlendModeDifference,
    'exclusion': kCGBlendModeExclusion,

    # Color component blend modes
    'hue': kCGBlendModeHue,
    'saturation': kCGBlendModeSaturation,
    'color': kCGBlendModeColor,
    'luminosity': kCGBlendModeLuminosity,

    # Porter-Duff compositing modes
    'sourcein': kCGBlendModeSourceIn,
    'sourceout': kCGBlendModeSourceOut,
    'sourceatop': kCGBlendModeSourceAtop,
    'destinationover': kCGBlendModeDestinationOver,
    'destinationin': kCGBlendModeDestinationIn,
    'destinationout': kCGBlendModeDestinationOut,
    'destinationatop': kCGBlendModeDestinationAtop,
    'xor': kCGBlendModeXOR,
    'plusdarker': kCGBlendModePlusDarker,
    'pluslighter': kCGBlendModePlusLighter,
}

# Human-readable list of blend modes for error messages
BLEND_MODES = """Available blend modes:
    Basic: normal, clear, copy
    
    Standard: multiply, screen, overlay, darken, lighten,
             color-dodge, color-burn, soft-light, hard-light,
             difference, exclusion
             
    Color: hue, saturation, color, luminosity
    
    Advanced: source-in, source-out, source-atop,
             destination-over, destination-in, destination-out, destination-atop,
             xor, plusdarker, pluslighter"""


### Effects objects ###

class Frob(object):
    """A FoRmatting OBject encapsulates changes to the graphics context state.

    It can be appended to the current canvas for a one-shot change or pushed onto the
    canvas to perform a reset once the associated with block completes.
    """
    _grobs = None

    def append(self, grob):
        if self._grobs is None:
            self._grobs = []
        self._grobs.append(grob)

    def _draw(self):
        # apply state changes only to contained grobs
        with _cg_context(), self.applied():
            if not self._grobs:
                return
            for grob in self._grobs:
                grob._draw()

    @property
    def contents(self):
        return self._grobs or []

class Effect(Frob):
    """Manages graphical effects (blend modes, alpha, shadows, and rasterization) in the graphics context.
    
    Effects can be used either as a context manager:
        with Effect(blend='multiply', alpha=0.5):
            # drawing code here
    
    Or applied directly:
        effect = Effect(shadow=(0,10,5))
        effect.append(some_grob)
    """
    kwargs = ('blend','alpha','shadow','raster')

    def __init__(self, *args, **kwargs):
        self._fx = {}
        # Initialize effect settings (ignoring any rollback flag)
        if kwargs.pop('rollback', False):
            self._rollback = {eff:getattr(_ctx._effects, eff) for eff in kwargs}

        for eff, val in kwargs.items():
            self._fx[eff] = Effect._validate(eff, val)

    def __repr__(self):
        return "Effect(%r)" % self._fx

    def __enter__(self):
        # if this isn't the first pass through the context manager, snapshot the current
        # state for all the effects we're changing so they can be restored in __exit__
        if not hasattr(self, '_rollback'):
            self._rollback = {eff:val for eff,val in _ctx._effects._fx.items() if eff in self._fx}

        # concat ourseves as a new canvas container
        _ctx.canvas.push(self)

        # reset the global per-object effects state within the block (since the effects
        # will be applied to a transparency layer encapsulating all drawing)
        for eff in self._fx:
            _ctx._effects._fx.pop(eff, None)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        _ctx.canvas.pop()

        # restore the per-object effects state to what it was before the `with` block
        for eff, val in self._rollback.items():
            setattr(_ctx._effects, eff, val)
        del self._rollback

    def apply_alpha(self):
        """Apply alpha settings to the current graphics context.
        
        Returns True if alpha was applied, False otherwise.
        """
        if 'alpha' in self._fx:
            CGContextSetAlpha(_cg_port(), self._fx['alpha'])
            return True
        return False

    def apply_blend(self):
        """Apply blend mode settings to the current graphics context.
        
        Returns True if blend mode was applied, False otherwise.
        """
        if 'blend' in self._fx:
            CGContextSetBlendMode(_cg_port(), _BLEND[self._fx['blend']])
            return True
        return False

    def apply_blend_alpha(self):
        """Apply both blend and alpha settings to the current graphics context.
        
        These effects share a transparency layer and must be applied together.
        Returns True if either effect was applied.
        """
        blend_applied = self.apply_blend()
        alpha_applied = self.apply_alpha()
        return blend_applied or alpha_applied

    def apply_shadow(self):
        """Apply shadow settings to the current graphics context.
        
        Shadow requires its own transparency layer separate from blend/alpha.
        Returns True if shadow was applied.
        """
        if 'shadow' in self._fx:
            shadow = Shadow(None) if self._fx['shadow'] is None else self._fx['shadow']
            shadow._nsShadow.set()  # Shadow is applied via Cocoa API
            return True
        return False

    def apply_raster(self):
        """Apply rasterization settings to the current graphics context.
        
        Rasterization requires its own image context.
        Returns True if rasterization was applied.
        """
        if 'raster' in self._fx:
            if self._fx['raster'] is True:
                raster = Raster()
                return True
        return False

    @contextmanager
    def applied(self):
        """Apply effects within appropriate transparency layers.
        
        The effects are applied in a specific order and with specific layer requirements:
        - blend/alpha effects are applied together and require their own transparency layer
        - shadow requires its own transparency layer
        - raster requires its own image context
        - if only one type is present, it gets a single layer
        
        Layer structure:
        1. blend/alpha layer (if either effect is present)
            2. shadow layer (if shadow is present)
                3. raster context (if raster is present)
                    --> drawing occurs here <--
        """
        if not self._fx:
            yield  # no effects to apply
            return

        with ExitStack() as stack:
            # First check if we need a layer for blend/alpha effects
            # These effects work together and share a transparency layer
            if self.apply_blend_alpha():
                stack.enter_context(_cg_layer())
            
            # If we also have a shadow, it needs its own nested layer
            # This ensures the shadow renders correctly with the blend/alpha effects
            if self.apply_shadow():
                stack.enter_context(_cg_layer())
            
            if self.apply_raster():
                stack.enter_context(Raster().applied())
        
            # All effects are now applied and layers are set up
            # Drawing will occur within the innermost active layer
            yield

    def copy(self):
        new_effect = Effect()
        new_effect._fx = self._fx.copy()
        return new_effect

    @classmethod
    def _validate(cls, eff, val):
        """Validate and normalize effect values.
        
        Args:
            eff: Effect type ('blend', 'alpha', 'shadow', or 'raster')
            val: Value to validate
            
        Returns:
            Normalized value if valid
            
        Raises:
            DeviceError: If value is invalid for the effect type
        """
        if val is None:
            return None
        elif eff == 'alpha':
            if not (numlike(val) and 0 <= val <= 1):
                raise DeviceError("alpha() value must be a number between 0 and 1.0")
        elif eff == 'blend':
            val = re.sub(r'[_\- ]', '', val).lower()
            if val not in _BLEND:
                raise DeviceError('"%s" is not a recognized blend mode.\nUse one of:\n%s'
                                  % (val, BLEND_MODES))
        elif eff == 'shadow':
            if isinstance(val, Shadow):
                return val.copy()
            else:
                return Shadow(*val)
        elif eff == 'raster':
            return bool(val)
        return val

    @property
    def alpha(self):
        return self._fx.get('alpha', 1.0)

    @alpha.setter
    def alpha(self, a):
        if a is None:
            self._fx.pop('alpha', None)
        else:
            self._fx['alpha'] = self._validate('alpha', a)

    @property
    def blend(self):
        return self._fx.get('blend', 'normal')

    @blend.setter
    def blend(self, mode):
        if mode is None:
            self._fx.pop('blend', None)
        else:
            self._fx['blend'] = self._validate('blend', mode)

    @property
    def shadow(self):
        return self._fx.get('shadow', None)

    @shadow.setter
    def shadow(self, spec):
        if spec is None:
            self._fx.pop('shadow', None)
        else:
            self._fx['shadow'] = self._validate('shadow', spec)

    @property
    def raster(self):
        return self._fx.get('raster', False)
        
    @raster.setter
    def raster(self, enable):
        if enable is None:
            self._fx.pop('raster', None)
        else:
            self._fx['raster'] = self._validate('raster', enable)

class Shadow(object):
    """Manages shadow effects in the graphics context.
    
    A shadow can be configured with:
    - color: Color of the shadow (defaults to black at 75% opacity)
    - blur: Blur radius of the shadow (defaults to 10 or 0 if color alpha is 0)
    - offset: Shadow offset as (x,y) or single value for both (defaults to blur/2.0)
    """
    kwargs = ('color', 'blur', 'offset')

    def __init__(self, *args, **kwargs):
        super(Shadow, self).__init__()
        self._nsShadow = NSShadow.alloc().init()
        
        if args and isinstance(args[0], Shadow):
            # Copy constructor
            self._nsShadow = _copy_attr(args[0]._nsShadow)
            for attr, val in kwargs.items():
                if attr in self.kwargs:
                    setattr(self, attr, val)
        else:
            # Normal initialization
            for attr, val in zip(self.kwargs, args):
                kwargs.setdefault(attr, val)

            self.color = Color(kwargs.get('color', ('#000', .75)))
            self.blur = kwargs.get('blur', 10 if self.color.a else 0)
            offset = kwargs.get('offset', self.blur/2.0)
            if numlike(offset):
                offset = [offset]
            if len(offset)==1:
                offset *= 2
            self.offset = offset

    def __repr__(self):
        return "Shadow(%r, blur=%r, offset=%r)" % (self.color, self.blur, tuple(self.offset))

    def copy(self):
        return Shadow(self)

    @property
    def color(self):
        """The color of the shadow."""
        return Color(self._nsShadow.shadowColor())

    @color.setter
    def color(self, spec):
        if isinstance(spec, Color):
            self._nsShadow.setShadowColor_(spec.nsColor)
        elif spec is None:
            self._nsShadow.setShadowColor_(None)
        else:
            if not isinstance(spec, (tuple,list)):
                spec = tuple([spec])
            self._nsShadow.setShadowColor_(Color(*spec).nsColor)

    @property
    def blur(self):
        """The blur radius of the shadow."""
        return self._nsShadow.shadowBlurRadius()

    @blur.setter
    def blur(self, blur):
        self._nsShadow.setShadowBlurRadius_(blur)

    @property
    def offset(self):
        """The offset of the shadow as a Point(x,y)."""
        x,y = self._nsShadow.shadowOffset()
        return Point(x,-y)

    @offset.setter
    def offset(self, offset):
        if numlike(offset):
            x = y = offset
        else:
            x,y = offset
        self._nsShadow.setShadowOffset_((x,-y))

class Stencil(Frob):
    """Manages stencil/clipping mask effects in the graphics context.
    
    A stencil creates a mask that determines which areas will be drawn.
    It can be created from different source types:
    
    Text:
        Uses the text path as a clipping mask
    Bezier:
        Uses the path as a clipping mask
    Image:
        Uses image data as a clipping mask, using either:
        - alpha channel (if available)
        - luminance/darkness (if no alpha)
        
    Args:
        stencil: Source object (Text, Bezier, or Image)
        invert: Whether to invert the mask (default: False)
        channel: For images, which channel to use ('alpha', 'black', etc)
    """
    def __init__(self, stencil, invert=False, channel=None):
        from .text import Text
        from .bezier import Bezier
        from .image import Image

        if isinstance(stencil, (Text, Bezier)):
            # for Text/Bezier stencils, we use the path as a clipping mask
            # the evenodd flag determines whether to use even-odd fill rule:
            # - when False (default): Areas inside the path are visible
            # - when True (inverted): Areas outside the path are visible
            self.path = stencil.path if isinstance(stencil, Text) else stencil.copy()
            self.evenodd = invert
        elif isinstance(stencil, Image):
            self.bmp = stencil
            # default to using alpha if available and darkness if not
            self.channel = channel or ('alpha' if stencil._nsBitmap.hasAlpha() else 'black')
            # for 'black' channel we invert since we want dark areas to show through
            # (opposite of alpha/rgb channels where white/opaque areas show through)
            self.invert = invert if self.channel != 'black' else not invert

    def __repr__(self):
        if hasattr(self, 'path'):
            return "Stencil(path, invert=%r)" % self.evenodd
        return "Stencil(image, channel=%r, invert=%r)" % (self.channel, self.invert)

    def set(self):
        """Apply the stencil to the current graphics context."""
        port = _cg_port()

        if hasattr(self, 'path'):
            path_xf = self.path._screen_transform
            cg_path = path_xf.apply(self.path).cgPath
            CGContextBeginPath(port)
            if self.evenodd:
                # if inverted, knock the path out of a full-screen rect and clip with that
                CGContextAddRect(port, ((0,0),(_ctx.WIDTH, _ctx.HEIGHT)))
                CGContextAddPath(port, cg_path)
                CGContextEOClip(port)
            else:
                # otherwise just color between the lines
                CGContextAddPath(port, cg_path)
                CGContextClip(port)

        elif hasattr(self, 'bmp'):
            # run the filter chain and render to a cg-image
            singlechannel = ciFilter(self.channel, self.bmp._ciImage)
            greyscale = ciFilter(self.invert, singlechannel)
            ci_ctx = CIContext.contextWithOptions_(None)
            maskRef = ci_ctx.createCGImage_fromRect_(greyscale, ((0,0), self.bmp.size))

            # turn the image into an 'imagemask' cg-image
            cg_mask = CGImageMaskCreate(
                CGImageGetWidth(maskRef),
                CGImageGetHeight(maskRef),
                CGImageGetBitsPerComponent(maskRef),
                CGImageGetBitsPerPixel(maskRef),
                CGImageGetBytesPerRow(maskRef),
                CGImageGetDataProvider(maskRef), 
                None, 
                False
            )

            # the mask is sitting at (0,0) until transformed to screen coords
            xf = self.bmp._screen_transform
            xf.concat() # apply transforms before clipping...
            CGContextClipToMask(port, ((0,0), self.bmp.size), cg_mask)
            xf.inverse.concat() # ...restore the previous state after

    @contextmanager
    def applied(self):
        """Apply the stencil effect within a context manager block."""
        self.set()
        yield

class ClippingPath(Stencil):
    pass # NodeBox compat...

class Raster(Frob):
    """Manages rasterization effects in the graphics context.
    
    Renders drawing commands into an offscreen image buffer before compositing
    back into the main graphics context.
    """
    def __init__(self):
        super(Raster, self).__init__()
        self._cgContext = None

    def __repr__(self):
        return "Raster()"

    def set(self):
        """Prepare the raster buffer for drawing.
        
        Unlike other effects that modify the current graphics context's state,
        rasterization requires creating an entirely new bitmap context and
        redirecting all drawing operations to it. This is why we perform a
        complete context switch rather than using the _ns_context() manager.
        """
        # Create bitmap context with same dimensions as canvas
        size = (_ctx.WIDTH, _ctx.HEIGHT)
        colorspace = CGColorSpaceCreateDeviceRGB()
        opts = kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Host
        self._cgContext = CGBitmapContextCreate(None, size[0], size[1], 8, size[0] * 4, colorspace, opts)
        
        # NOTE: This effect performs a full context switch rather than just state changes.
        # We need to redirect all drawing to a new bitmap context, which requires
        # replacing the current NSGraphicsContext entirely.
        ns_ctx = NSGraphicsContext.graphicsContextWithCGContext_flipped_(self._cgContext, True)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(ns_ctx)
        
        # Apply the current transform
        _ctx._transform.concat()

    def reset(self):
        """Composite the raster buffer and clean up.
        
        After drawing to the offscreen bitmap, we restore the original graphics
        context and draw the bitmap contents back to it.
        """
        if self._cgContext is not None:
            try:
                # Restore the original graphics context
                NSGraphicsContext.restoreGraphicsState()
                
                # Create an image from the bitmap context and draw it
                # to the original context we've now restored
                cgImage = CGBitmapContextCreateImage(self._cgContext)
                bounds = ((0, 0), (_ctx.WIDTH, _ctx.HEIGHT))
                CGContextDrawImage(_cg_port(), bounds, cgImage)
            finally:
                self._cgContext = None

    @contextmanager
    def applied(self):
        """Apply the raster effect within a context manager block.
        
        This follows a try/finally pattern to ensure proper cleanup
        of graphics resources even if an exception occurs.
        """
        try:
            self.set()
            yield
        finally:
            self.reset()

### core-image filters for channel separation and inversion ###

def ciFilter(opt, img):
    _filt = _inversionFilter if isinstance(opt, bool) else _channelFilter
    return _filt(opt, img)

def _channelFilter(channel, img):
    """Generate a greyscale image by isolating a single r/g/b/a channel"""

    rgb = ('red', 'green', 'blue')
    if channel=='alpha':
        transmat = [(0, 0, 0, 1)] * 3
        transmat += [ (0,0,0,0), (0,0,0,1) ]
    elif channel in rgb:
        rgb_row = [0,0,0]
        rgb_row.insert(rgb.index(channel), 1.0)
        transmat = [tuple(rgb_row)] * 3
        transmat += [ (0,0,0,0), (0,0,0,1) ]
    elif channel in ('black', 'white'):
        transmat = [(.333, .333, .333, 0)] * 3
        transmat += [ (0,0,0,0), (0,0,0,1) ]
    return _matrixFilter(transmat, img)

def _inversionFilter(identity, img):
    """Conditionally turn black to white and up to down"""

    # set up a matrix that's either identity or an r/g/b inversion
    polarity = -1.0 if not identity else 1.0
    bias = 0 if polarity>0 else 1
    transmat = [(polarity, 0, 0, 0), (0, polarity, 0, 0), (0, 0, polarity, 0),
                (0, 0, 0, 0), (bias, bias, bias, 1)]
    return _matrixFilter(transmat, img)

def _matrixFilter(matrix, img):
    """Apply a color transform to a CIImage and return the filtered result"""

    vectors = ("inputRVector", "inputGVector", "inputBVector", "inputAVector", "inputBiasVector")
    opts = {k:CIVector.vectorWithX_Y_Z_W_(*v) for k,v in zip(vectors, matrix)}
    opts[kCIInputImageKey] = img
    remap = CIFilter.filterWithName_("CIColorMatrix")
    for k,v in opts.items():
        remap.setValue_forKey_(v, k)
    return remap.valueForKey_("outputImage")