# encoding: utf-8
import re
import os
from math import floor
from .. import DeviceError
from ..util import trim_zeroes
from .colors import Color

# Variable types
NUMBER = "number"
TEXT = "text"
BOOLEAN = "boolean"
BUTTON = "button"
COLOR = "color"
SELECT = "select"
FILE = "file"

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
        self.label = re_punct.sub(r'\1:', kwargs.get('label', name))

        if self.type == COLOR:
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("COLOR value cannot be specified both positionally and as a keyword argument")
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
                raise DeviceError("NUMBER variable requires min and max values")
            self.min, self.max = args[0:2]
            self.min, self.max = min(self.min, self.max), max(self.min, self.max)
            
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
                if ((self.max-self.min) / self.step) % 1 > 0:
                    raise DeviceError("The step size %d doesn't fit evenly into the range %d–%d" % (self.step, self.min, self.max))
                self.value = self.step * floor((self.value + self.step/2) / self.step)

            if not self.min <= self.value <= self.max:
                raise DeviceError("The value %d doesn't fall within the range %d–%d" % (self.value, self.min, self.max))

        elif self.type == TEXT:
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("TEXT value cannot be specified both positionally and as a keyword argument")
            self.value = kwargs.get('value', args[0] if args else '')

        elif self.type == BOOLEAN:
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("BOOLEAN value cannot be specified both positionally and as a keyword argument")
            self.value = kwargs.get('value', args[0] if args else False)

        elif self.type == BUTTON:
            # Validate: color can't be both positional and kwarg
            if len(args) > 1 and 'color' in kwargs:
                raise DeviceError("Button color cannot be specified both positionally and as a keyword argument")
            self.value = args[0] if args else name
            clr = kwargs.get('color', args[1] if len(args) > 1 else None)
            self.color = Color(clr) if clr else None
            
        elif self.type == SELECT:
            # SELECT: Requires options list, optional value
            if not args:
                raise DeviceError("SELECT variable requires a list of options")
            options = args[0]
            if not isinstance(options, (list, tuple)):
                raise DeviceError("SELECT variable requires a list of options")
            if not options:
                raise DeviceError("SELECT variable requires at least one option")
            self.options = options
            # Validate: value can't be both positional and kwarg
            if len(args) > 1 and 'value' in kwargs:
                raise DeviceError("SELECT value cannot be specified both positionally and as a keyword argument")
            self.value = kwargs.get('value', args[1] if len(args) > 1 else options[0])
            if self.value not in options:
                raise DeviceError(f"Value '{self.value}' not found in options list")

        elif self.type == FILE:
            # FILE: Optional value and file types
            # Validate: value can't be both positional and kwarg
            if args and 'value' in kwargs:
                raise DeviceError("FILE path cannot be specified both positionally and as a keyword argument")
            
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
                self.value = max(self.min, min(self.max, old.value))
                if self.step:
                    self.value = self.step * floor((self.value + self.step/2) / self.step)
            elif self.type is COLOR:
                self.value = old.value
            else:
                self.value = old.value

    @trim_zeroes
    def __repr__(self):
        attrs = ['name', 'type', 'value', 'min', 'max', 'step', 'color', 'label']
        return "Variable(%s)" % ' '.join('%s=%s' % (a,getattr(self, a)) for a in attrs if hasattr(self, a)) 