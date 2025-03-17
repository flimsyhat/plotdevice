# encoding: utf-8
import re
import os
from math import floor
from .. import DeviceError
from ..util import trim_zeroes
from .colors import Color
import objc

# Variable types
NUMBER = "number"
TEXT = "text"
BOOLEAN = "boolean"
BUTTON = "button"
COLOR = "color"
SELECT = "select"
FILE = "file"

# Constants for UI limits
MAX_LABEL_LENGTH = 25  # Maximum characters for variable labels and button text

__all__ = ["Variable", "NUMBER", "TEXT", "BOOLEAN", "BUTTON", "COLOR", "SELECT", "FILE"]

re_var = re.compile(r'[A-Za-z_][A-Za-z0-9_]*$')
re_punct = re.compile(r'([^\!\'\#\%\&\'\(\)\*\+\,\-\.\/\:\;\<\=\>\?\@\[\/\]\^\_\{\|\}\~])$')

class Variable(object):
    def __init__(self, name, type, *args, **kwargs):
        if not re_var.match(name):
            raise DeviceError('Not a legal variable name: "%s"' % name)

        # Validate that type is one of the allowed variable types
        valid_types = (NUMBER, TEXT, BOOLEAN, BUTTON, COLOR, SELECT, FILE)
        if type not in valid_types:
            raise DeviceError(f"Invalid variable type: {type}. Must be one of: NUMBER, TEXT, BOOLEAN, BUTTON, COLOR, SELECT, or FILE")

        self.name = name
        self.type = type
        
        # Get label and truncate if too long
        raw_label = kwargs.get('label', name)
        if len(raw_label) > MAX_LABEL_LENGTH:
            raw_label = raw_label[:MAX_LABEL_LENGTH-1] + '…'
        self.label = re_punct.sub(r'\1:', raw_label)

        if self.type == COLOR:
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("Color value cannot be specified both positionally and as a keyword argument")
            color_str = kwargs.get('value', args[0] if args else '#cccccc')
            try:
                Color(color_str)
                self.value = color_str
            except:
                badcolor = "Invalid color specification for variable '%s': %r"%(name, color_str)
                raise DeviceError(badcolor)

        elif self.type == NUMBER:
            # NUMBER: Requires min/max, optional step/value
            if len(args) < 2:
                raise DeviceError("Number variable requires min and max values")
            
            # Validate min/max are valid floats and within bounds
            try:
                self.min = float(args[0])
                self.max = float(args[1])
                
                # Set reasonable bounds to ensure NSSlider works reliably and doesn't crash for really large values
                MAX_SLIDER = 1e6  # Million
                MIN_SLIDER = -1e6 # Negative million
                
                if not (MIN_SLIDER <= self.min <= MAX_SLIDER):
                    raise DeviceError(f"Min value {self.min} is outside valid range ({MIN_SLIDER} to {MAX_SLIDER})")
                if not (MIN_SLIDER <= self.max <= MAX_SLIDER):
                    raise DeviceError(f"Max value {self.max} is outside valid range ({MIN_SLIDER} to {MAX_SLIDER})")
            except (ValueError, TypeError):
                raise DeviceError("Min and max values must be valid numbers")
            
            # Warn if range is inverted (but still handle it)
            if self.min > self.max:
                import warnings
                warnings.warn(f"Range is inverted: min ({self.min}) > max ({self.max}). Values will be swapped.")
                self.min, self.max = self.max, self.min
            
            # Validate: step/value can't be both positional and kwargs
            remaining_args = args[2:]
            if len(remaining_args) > 0 and 'step' in kwargs:
                raise DeviceError("Step value cannot be specified both positionally and as a keyword argument")
            if len(remaining_args) > 1 and 'value' in kwargs:
                raise DeviceError("Value cannot be specified both positionally and as a keyword argument")
            
            # First optional arg is step, second is value
            self.step = kwargs.get('step', remaining_args[0] if remaining_args else None)
            self.value = kwargs.get('value', remaining_args[1] if len(remaining_args) > 1 else self.min)

            if self.step:
                # No validation needed - we'll just use the step size as provided
                # and let the slider handle any partial steps at the end
                
                # Just ensure the value aligns with steps
                self.value = min(self.max, max(self.min, 
                    self.min + self.step * floor((self.value - self.min + self.step/2) / self.step)
                ))

            if not self.min <= self.value <= self.max:
                raise DeviceError("The value %g doesn't fall within the range %g–%g" % (self.value, self.min, self.max))

        elif self.type == TEXT:
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("Text value cannot be specified both positionally and as a keyword argument")
            
            # Get value and filter out control characters (newlines, tabs, etc)
            # This ensures the initial/default value is clean
            raw_value = kwargs.get('value', args[0] if args else '')
            self.value = ''.join(c for c in str(raw_value) if c.isprintable() or c == ' ')

        elif self.type == BOOLEAN:
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("Boolean value cannot be specified both positionally and as a keyword argument")
            self.value = kwargs.get('value', args[0] if args else False)

        elif self.type == BUTTON:
            # Validate: color can't be both positional and kwarg
            if len(args) > 1 and 'color' in kwargs:
                raise DeviceError("Button color cannot be specified both positionally and as a keyword argument")
            
            # Get label and truncate if too long (25 characters)
            label = args[0] if args else name
            if len(label) > MAX_LABEL_LENGTH:
                label = label[:MAX_LABEL_LENGTH-1] + '…'
            self.value = label
            
            # Handle color
            clr = kwargs.get('color', args[1] if len(args) > 1 else None)
            self.color = Color(clr) if clr else None
            
        elif self.type == SELECT:
            # SELECT: Requires options list, optional value
            if not args:
                raise DeviceError("Select variable requires a list of options")
            options = args[0]
            if not isinstance(options, (list, tuple)):
                raise DeviceError("Select variable requires a list of options")
            if not options:
                raise DeviceError("Select variable requires at least one option")
            
            # Store both original values and their string representations
            self.options = options
            self._display_options = [str(opt) for opt in options]
            
            # Validate: value can't be both positional and kwarg
            if len(args) > 1 and 'value' in kwargs:
                raise DeviceError("Select value cannot be specified both positionally and as a keyword argument")
            
            # Get value
            self.value = kwargs.get('value', args[1] if len(args) > 1 else options[0])
            
            # Validate value is in options
            if self.value not in options:
                raise DeviceError(f"Value '{self.value}' not found in options list")

        elif self.type == FILE:
            # FILE: Optional value and file types
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("File path cannot be specified both positionally and as a keyword argument")
            
            # Get allowed file types (optional)
            if len(args) > 1 and 'types' in kwargs:
                raise DeviceError("File types cannot be specified both positionally and as a keyword argument")
            
            # Process file types
            raw_types = kwargs.get('types', args[1] if len(args) > 1 else [])
            self.types = []
            if raw_types:
                # Normalize file types (remove dots, convert to lowercase)
                self.types = [t.lower().lstrip('.') for t in raw_types] if isinstance(raw_types, (list, tuple)) else [raw_types.lower().lstrip('.')]
            
            # Default to empty path
            self.value = ""
            
            # Get file path (optional)
            path = kwargs.get('value', args[0] if args else '')
            
            # If a default path is provided, check for file validity
            if path:
                # Check if path exists
                if not os.path.exists(path):
                    raise DeviceError(f"File not found: '{path}'")
                
                # Check if it's a file (not a directory)
                if not os.path.isfile(path):
                    raise DeviceError(f"Path is not a file: '{path}'")
                
                # Check file type if types are specified
                if self.types:
                    ext = os.path.splitext(path)[1].lower().lstrip('.')
                    if not ext:
                        raise DeviceError(f"File has no extension: '{path}'")
                    if ext not in self.types:
                        allowed = ', '.join(f'.{t}' for t in self.types)
                        raise DeviceError(f"File type '.{ext}' not allowed. Must be one of: {allowed}")
                
                # All checks passed, set the value
                self.value = path

    def inherit(self, old=None):
        if old and old.type is self.type:
            if self.type is NUMBER:
                try:
                    old_value = float(old.value) if isinstance(old.value, (str, objc.pyobjc_unicode)) else old.value
                    self.value = round(max(self.min, min(self.max, old_value)), 3)
                    if self.step:
                        self.value = self.step * floor((self.value + self.step/2) / self.step)
                except (ValueError, TypeError):
                    self.value = self.min
            elif self.type is COLOR:
                self.value = old.value
            else:
                self.value = old.value

    @trim_zeroes
    def __repr__(self):
        attrs = ['name', 'type', 'value', 'min', 'max', 'step', 'color', 'label']
        return "Variable(%s)" % ' '.join('%s=%s' % (a,getattr(self, a)) for a in attrs if hasattr(self, a)) 