# encoding: utf-8
import os, re
from collections import OrderedDict
from ..lib.cocoa import *
from math import floor, ceil
import objc
from ..gfx.colors import Color
from ..gfx.variables import NUMBER, TEXT, BOOLEAN, BUTTON, COLOR, SELECT, FILE

## classes instantiated by PlotDeviceDocument.xib & PlotDeviceScript.xib

class StatusView(NSView):
    spinner = IBOutlet()
    counter = IBOutlet()
    cancel = IBOutlet()

    def awakeFromNib(self):
        self.cancel.setHidden_(True)
        self._state = 'idle'
        self._finishing = False

        opts = (NSTrackingMouseEnteredAndExited | NSTrackingActiveInActiveApp);
        trackingArea = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(self.bounds(), opts, self, None)
        self.addTrackingArea_(trackingArea)

        self.cancel.cell().setHighlightsBy_(NSContentsCellMask)
        self.cancel.cell().setShowsStateBy_(NSContentsCellMask)
        self.counter.setHidden_(True)

    def beginExport(self):
        self._state = 'run'

        self.spinner.stopAnimation_(None)
        self.cancel.setHidden_(True)
        self.spinner.setIndeterminate_(False)
        self.spinner.setDoubleValue_(0)
        self.spinner.startAnimation_(None)

        self.counter.setHidden_(False)
        self.counter.setStringValue_("")

    def updateExport_total_(self, written, total):
        self.spinner.setMaxValue_(total)
        self.spinner.setDoubleValue_(written)
        msg = "Frame {:,}/{:,}".format(written, total) if written<total else "Finishing…"
        self.counter.setStringValue_(msg)

    def finishExport(self):
        if self._state == 'run':
            self.cancel.setHidden_(True)
            self.spinner.setHidden_(False)
            self.spinner.stopAnimation_(None)
            self.spinner.setIndeterminate_(True)
            self.spinner.startAnimation_(None)
            self._state = 'finish'
            self.counter.setStringValue_("Finishing export")
            return True

    def endExport(self):
        self.spinner.setIndeterminate_(True)
        self.spinner.stopAnimation_(None)
        self.cancel.setHidden_(True)
        self.counter.setHidden_(True)
        self._state = 'idle'

    def mouseEntered_(self, e):
        if self._state == 'run':
            self.cancel.setHidden_(False)
            self.spinner.setHidden_(True)

    def mouseExited_(self, e):
        self.cancel.setHidden_(True)
        self.spinner.setHidden_(False)


from ..context import NUMBER, TEXT, BOOLEAN, BUTTON
SMALL_FONT = NSFont.systemFontOfSize_(NSFont.smallSystemFontSize())
MINI_FONT = NSFont.systemFontOfSize_(NSFont.systemFontSizeForControlSize_(NSMiniControlSize))

class DashboardSwitch(NSSwitch):
    def acceptsFirstMouse_(self, e):
        return True

class DashboardRow(NSView):
    # Base layout measurements, using standard macOS sizes for small controls
    MARGIN_LEFT = 8         # Left margin of the entire row
    MARGIN_RIGHT = 8        # Right margin of the entire row
    ROW_HEIGHT = 22        # Standard small control row height
    CONTROL_HEIGHT = 19    # Standard small control height
    LABEL_PADDING = 8      # Space between the label and its control
    
    # Fine-tuning offsets for each control type
    # X offsets adjust horizontal position (negative = left, positive = right)
    # Y offsets adjust vertical position (negative = down, positive = up)
    TEXT_X_OFFSET = 2
    TEXT_Y_OFFSET = 0
    
    BOOLEAN_X_OFFSET = 1    # Checkbox position adjustments
    BOOLEAN_Y_OFFSET = -2
    
    NUMBER_X_OFFSET = 1     # Slider position adjustments
    NUMBER_Y_OFFSET = 0
    NUMBER_FIELD_Y_OFFSET = 1   # Move number field up slightly to align with slider
    
    BUTTON_X_OFFSET = -3    # Button position adjustments
    BUTTON_Y_OFFSET = -6
    
    COLOR_X_OFFSET = 0      # Color well position adjustments
    COLOR_Y_OFFSET = -1
    
    SELECT_X_OFFSET = -1    # Dropdown menu position adjustments
    SELECT_Y_OFFSET = -1
    
    FILE_BUTTON_X_OFFSET = -3   # File browser button position adjustments
    FILE_BUTTON_Y_OFFSET = -2
    FILE_PATH_X_OFFSET = -2     # File path display position adjustments
    FILE_PATH_Y_OFFSET = 0
    
    def initWithVariable_forDelegate_(self, var, delegate):
        self.initWithFrame_(((0,-999), (200, 30)))
        self.setAutoresizingMask_(NSViewWidthSizable)

        label = NSTextField.alloc().init()
        if var.label is not None:
            label.setStringValue_(var.label)
        label.setAlignment_(NSRightTextAlignment)
        label.setEditable_(False)
        label.setBordered_(False)
        label.setDrawsBackground_(False)
        label.setFont_(SMALL_FONT)
        label.sizeToFit()
        self.addSubview_(label)

        if var.type is TEXT:
            control = NSTextField.alloc().init()
            control.setStringValue_(var.value)
            control.cell().setControlSize_(NSSmallControlSize)
            control.setFont_(SMALL_FONT)
            control.setTarget_(self)
            control.setAutoresizingMask_(NSViewWidthSizable)
            control.setDelegate_(self)
            control.sizeToFit()
            self.addSubview_(control)

        elif var.type is BOOLEAN:
            control = DashboardSwitch.alloc().init()
            control.setState_(NSOnState if var.value else NSOffState)
            control.setControlSize_(NSSmallControlSize)
            control.sizeToFit()
            control.setFont_(SMALL_FONT)
            control.setTarget_(self)
            control.setAction_(objc.selector(self.booleanChanged_, signature=b"v@:@@"))
            self.addSubview_(control)

        elif var.type is NUMBER:
            control = NSSlider.alloc().init()
            control.setMaxValue_(var.max)
            control.setMinValue_(var.min)
            control.setFloatValue_(var.value)
            control.cell().setControlSize_(NSSmallControlSize)
            control.setContinuous_(True)
            control.setTarget_(self)
            control.setAutoresizingMask_(NSViewWidthSizable)
            control.setAction_(objc.selector(self.numberChanged_, signature=b"v@:@@"))
            self.addSubview_(control)

            # Create a standard text field with border
            num = NSTextField.alloc().init()
            num.setBordered_(True)
            num.setEditable_(True)
            num.setAutoresizingMask_(NSViewMinXMargin)
            num.setSelectable_(True)
            num.setDrawsBackground_(True)
            num.setFont_(SMALL_FONT)
            num.setDelegate_(self)  # Set delegate to handle text changes
            
            # Use a standard width instead of calculating based on possible values
            standard_num_width = 40
            num.setStringValue_(self._fmt(var.value))
            num.setFrameSize_((standard_num_width, 18))
            self.addSubview_(num)
            self.step = var.step
            self.num = num
            self.num_w = standard_num_width  # Store the width for layout
            
            # Add action to handle text field changes
            num.setAction_(objc.selector(self.controlTextDidEndEditing_, signature=b"v@:@@"))

        elif var.type is BUTTON:
            control = NSButton.alloc().init()
            control.setTitle_(var.value)
            control.setBezelStyle_(1)
            control.setFont_(SMALL_FONT)
            control.cell().setControlSize_(NSSmallControlSize)
            control.setTarget_(self)
            control.sizeToFit()
            control.setBezelColor_(getattr(var.color, '_rgb', None))
            control.setAction_(objc.selector(self.buttonClicked_, signature=b"v@:@@"))
            self.addSubview_(control)

        elif var.type is COLOR:
            control = NSColorWell.alloc().init()
            control.setColor_(Color(var.value).nsColor)
            control.setTarget_(self)
            control.setAction_(objc.selector(self.colorChanged_, signature=b"v@:@@"))
            control.sizeToFit()
            self.addSubview_(control)

        elif var.type is SELECT:
            control = NSPopUpButton.alloc().init()
            control.addItemsWithTitles_(var.options)
            control.selectItemWithTitle_(var.value)
            control.setTarget_(self)
            control.setAction_(objc.selector(self.selectChanged_, signature=b"v@:@@"))
            control.cell().setControlSize_(NSSmallControlSize)
            control.sizeToFit()
            self.addSubview_(control)

        elif var.type is FILE:
            # Create a container view
            container = NSView.alloc().init()
            
            if var.value:
                # If we have a path, show only the path control
                pathControl = NSPathControl.alloc().init()
                self._configure_path_control(pathControl, NSURL.fileURLWithPath_(var.value))
                container.addSubview_(pathControl)
                self.filePathControl = pathControl
            else:
                # If no path, show only the browse button
                button = NSButton.alloc().init()
                button.setTitle_("Browse...")
                button.setBezelStyle_(1)
                button.setFont_(SMALL_FONT)
                button.cell().setControlSize_(NSSmallControlSize)
                button.setTarget_(self)
                button.setAction_(objc.selector(self.browseForFile_, signature=b"v@:@@"))
                container.addSubview_(button)
                self.fileButton = button
            
            control = container
            self.addSubview_(control)

        self.name = var.name
        self.type = var.type
        self.label = label
        self.control = control
        self.button_w = control.frame().size.width if var.type is BUTTON else 0
        self.label_w = label.frame().size.width
        self.delegate = delegate
        return self

    @objc.python_method
    def _fmt(self, num):
        """Format number with up to 3 decimal places"""
        # Format with 3 decimal places and strip trailing zeros/decimal
        s = "{:.3f}".format(num).rstrip('0').rstrip('.')
        return s

    @objc.python_method
    def _num_w(self, lo, hi, step):
        num_w = 0
        inc = step if step else (hi - lo) / 97
        num = NSTextField.alloc().init()
        num.setFont_(SMALL_FONT)
        for i in range(1+ceil((hi - lo) / inc)):
            n = min(hi, lo + i*inc)
            s = self._fmt(n)
            num.setStringValue_(s)
            num.sizeToFit()
            num_w = max(num_w, num.frame().size.width)
        return num_w

    @objc.python_method
    def roundOff(self):
        if self.step:
            rounded = self.step * floor((self.control.floatValue() + self.step/2) / self.step)
            self.control.cell().setFloatValue_(rounded)
        self.num.setStringValue_(self._fmt(self.control.floatValue()))

    @objc.python_method
    def updateConfig(self, var):
        label = self.label
        control = self.control
        label.setStringValue_(var.label or '')
        label.sizeToFit()
        self.label_w = label.frame().size.width

        if var.type is NUMBER:
            control.setMaxValue_(var.max)
            control.setMinValue_(var.min)
            self.step = var.step
            self.roundOff()

        elif var.type is BUTTON:
            control.setTitle_(var.value)
            self.button_w = control.frame().size.width
            control.setBezelColor_(getattr(var.color, '_rgb', None))

        elif var.type is COLOR:
            control.setColor_(Color(var.value).nsColor)

        elif var.type is SELECT:
            control.removeAllItems()
            control.addItemsWithTitles_(var.options)
            control.selectItemWithTitle_(var.value)

        elif var.type is FILE:
            if var.value:
                url = NSURL.fileURLWithPath_(var.value)
                if hasattr(self, 'filePathControl'):
                    self._configure_path_control(self.filePathControl, url)
            elif hasattr(self, 'fileButton'):
                self.fileButton.setHidden_(False)

    @objc.python_method
    def updateLayout(self, indent, width, row_width, offset):
        # Base row frame
        self.setFrame_(((0, offset), (row_width, self.ROW_HEIGHT)))
        
        # Center label vertically
        label_height = self.label.frame().size.height
        label_y = (self.ROW_HEIGHT - label_height) / 2
        control_y = (self.ROW_HEIGHT - self.CONTROL_HEIGHT) / 2
        
        # Position label with right alignment - use label's natural width
        label_width = self.label_w
        label_x = indent - label_width
        self.label.setFrame_(((label_x, label_y), 
                             (label_width, label_height)))
        
        # Available width for controls
        control_width = width - indent - self.MARGIN_RIGHT
        
        # Position control based on type with consistent offsets
        if self.type is TEXT:
            text_height = self.control.frame().size.height
            text_y = (self.ROW_HEIGHT - text_height) / 2 + self.TEXT_Y_OFFSET
            # Adjust width by 1px while maintaining autoresizing behavior
            frame = ((indent + self.TEXT_X_OFFSET, text_y), 
                    (control_width - 1, text_height))
            self.control.setFrame_(frame)
        elif self.type is BOOLEAN:
            self.control.setFrameOrigin_((indent + self.BOOLEAN_X_OFFSET, 
                                         control_y + self.BOOLEAN_Y_OFFSET))
        elif self.type is NUMBER:
            slider_width = control_width - self.num_w - 10
            self.control.setFrame_(((indent + self.NUMBER_X_OFFSET, control_y + self.NUMBER_Y_OFFSET), 
                                   (slider_width, self.CONTROL_HEIGHT)))
            num_y = control_y + self.NUMBER_Y_OFFSET + self.NUMBER_FIELD_Y_OFFSET
            self.num.setFrameOrigin_((indent + slider_width + 10, num_y))
        elif self.type is BUTTON:
            self.control.setFrameOrigin_((indent + self.BUTTON_X_OFFSET, 
                                         control_y + self.BUTTON_Y_OFFSET))
        elif self.type is COLOR:
            self.control.setFrame_(((indent + self.COLOR_X_OFFSET, control_y + self.COLOR_Y_OFFSET), 
                                   (44, self.CONTROL_HEIGHT)))
        elif self.type is SELECT:
            self.control.setFrame_(((indent + self.SELECT_X_OFFSET, control_y + self.SELECT_Y_OFFSET), 
                                   (control_width, self.CONTROL_HEIGHT)))
            self.control.cell().setControlSize_(NSSmallControlSize)
            self.control.setFont_(SMALL_FONT)
        elif self.type is FILE:
            # Layout container
            self.control.setFrame_(((indent, control_y), 
                                   (control_width, self.CONTROL_HEIGHT)))
            
            # Layout the single control (either path or button)
            if hasattr(self, 'filePathControl'):
                self.filePathControl.setFrame_(((self.FILE_PATH_X_OFFSET, self.FILE_PATH_Y_OFFSET), 
                                              (control_width, self.CONTROL_HEIGHT)))
            elif hasattr(self, 'fileButton'):
                self.fileButton.setFrame_(((self.FILE_BUTTON_X_OFFSET, self.FILE_BUTTON_Y_OFFSET), 
                                          (80, self.CONTROL_HEIGHT)))

    def numberChanged_(self, sender):
        self.roundOff()
        if self.delegate:
            self.delegate.setVariable_to_(self.name, sender.floatValue())

    def controlTextDidChange_(self, note):
        """Handle changes to text variables as they're typed"""
        sender = note.object()
        
        # Only process for TEXT variables, not NUMBER variables
        if self.type is TEXT and self.delegate:
            self.delegate.setVariable_to_(self.name, sender.stringValue())

    def controlTextDidEndEditing_(self, notification):
        """Handle when user finishes editing text in a text field"""
        sender = notification.object()
        
        # Check if this is our number field
        if hasattr(self, 'num') and sender == self.num:
            try:
                # Try to parse the value as a float
                value_str = sender.stringValue()
                value = float(value_str.replace(',', ''))
                
                # Constrain to min/max
                value = max(self.control.minValue(), min(self.control.maxValue(), value))
                
                # Apply step if needed
                if self.step:
                    value = self.step * floor((value + self.step/2) / self.step)
                
                # Update the slider
                self.control.setFloatValue_(value)
                
                # Update the text field with properly formatted value
                sender.setStringValue_(self._fmt(value))
                
                # Notify delegate
                if self.delegate:
                    self.delegate.setVariable_to_(self.name, value)
            except ValueError:
                # If parsing fails, reset to current slider value
                sender.setStringValue_(self._fmt(self.control.floatValue()))

    def booleanChanged_(self, sender):
        if self.delegate:
            self.delegate.setVariable_to_(self.name, sender.state() == NSOnState)

    def buttonClicked_(self, sender):
        if self.delegate:
            self.delegate.callHandler_(self.name)

    def colorChanged_(self, sender):
        if self.delegate:
            color = sender.color()
            
            # Try to get RGB values first
            try:
                r, g, b, a = color.getRed_green_blue_alpha_(None, None, None, None)
                hex_color = "#{:02x}{:02x}{:02x}".format(
                    int(r * 255), 
                    int(g * 255), 
                    int(b * 255)
                )
            except ValueError:
                # If RGB fails, try grayscale
                try:
                    w, a = color.getWhite_alpha_(None, None)
                    hex_color = "#{:02x}{:02x}{:02x}".format(
                        int(w * 255),
                        int(w * 255),
                        int(w * 255)
                    )
                except ValueError:
                    # If grayscale fails, try CMYK
                    try:
                        c, m, y, k, a = color.getCyan_magenta_yellow_black_alpha_(None, None, None, None, None)
                        # Convert to RGB first (using Color class's conversion)
                        rgb_color = Color(CMYK, c, m, y, k)
                        r, g, b = rgb_color.rgba[:3]
                        hex_color = "#{:02x}{:02x}{:02x}".format(
                            int(r * 255),
                            int(g * 255),
                            int(b * 255)
                        )
                    except:
                        # If all conversions fail, default to black
                        hex_color = "#000000"
            
            self.delegate.setVariable_to_(self.name, hex_color)

    def selectChanged_(self, sender):
        if self.delegate:
            self.delegate.setVariable_to_(self.name, sender.titleOfSelectedItem())

    def browseForFile_(self, sender):
        # Create open panel
        openPanel = NSOpenPanel.openPanel()
        openPanel.setCanChooseFiles_(True)
        openPanel.setCanChooseDirectories_(False)
        openPanel.setAllowsMultipleSelection_(False)
        
        # Set allowed file types if specified
        if self.delegate and hasattr(self.delegate, 'script'):
            var = self.delegate.script.vm.params[self.name]
            if var.types:
                openPanel.setAllowedFileTypes_(var.types)
        
        # If we have a current file, start in its directory
        if hasattr(self, 'filePathControl'):
            current_url = self.filePathControl.URL()
            if current_url:
                # Get the directory containing the current file
                directory_url = current_url.URLByDeletingLastPathComponent()
                openPanel.setDirectoryURL_(directory_url)
        
        # Show the panel
        result = openPanel.runModal()
        if result == NSModalResponseOK:
            url = openPanel.URLs()[0]
            path = url.path()
            
            # Remove existing path control if it exists
            if hasattr(self, 'filePathControl'):
                self.filePathControl.removeFromSuperview()
            
            # Remove the button if it exists
            if hasattr(self, 'fileButton'):
                self.fileButton.removeFromSuperview()
                del self.fileButton
            
            # Create and add the path control
            pathControl = NSPathControl.alloc().init()
            self._configure_path_control(pathControl, url)
            pathControl.setFrame_(((0, 0), (self.control.frame().size.width, self.CONTROL_HEIGHT)))
            self.control.addSubview_(pathControl)
            self.filePathControl = pathControl
            
            if self.delegate:
                self.delegate.setVariable_to_(self.name, path)

    @objc.python_method
    def _configure_path_control(self, pathControl, url):
        """Configure an NSPathControl with our standard settings"""
        # Set size and style
        pathControl.cell().setControlSize_(NSSmallControlSize)
        pathControl.setFont_(SMALL_FONT)
        
        # Set URL
        pathControl.setURL_(url)
        pathControl.setEditable_(False)
        pathControl.setPathStyle_(0)  # NSPathStyleStandard
        pathControl.setBackgroundColor_(NSColor.clearColor())
        
        # Configure component cells
        components = pathControl.pathComponentCells()
        if len(components) > 2:
            last_components = components[-2:]
            for cell in last_components:
                cell.setBordered_(False)
                cell.setBackgroundStyle_(0)
                cell.setFont_(SMALL_FONT)
                cell.setControlSize_(NSSmallControlSize)
            pathControl.setPathComponentCells_(last_components)
        
        # Add tooltip for full path
        pathControl.setToolTip_(url.path())
        
        # Make it clickable to choose a file
        pathControl.setTarget_(self)
        pathControl.setAction_(objc.selector(self.browseForFile_, signature=b"v@:@@"))

    @objc.python_method
    def _truncate_path_components(self, pathControl):
        """Show only the last folder and filename in the path control"""
        components = pathControl.pathComponentCells()
        if len(components) > 2:
            pathControl.setPathComponentCells_(components[-2:])

class DashboardController(NSObject):
    script = IBOutlet()
    panel = IBOutlet()

    # Layout constants
    PANEL_TOP_PADDING = 5    # Space at top of panel
    PANEL_BOTTOM_PADDING = 25 # Space at bottom of panel
    MIN_CONTROL_WIDTH = 200   # Minimum width for controls
    MAX_WIDTH_MULTIPLIER = 5  # Maximum panel width multiplier
    TITLE_BAR_HEIGHT = 38    # Height of window title bar

    def awakeFromNib(self):
        self.panel.contentView().setFlipped_(True)
        self.rows = OrderedDict()
        
        # Register for script lifecycle notifications
        nc = NSNotificationCenter.defaultCenter()
        self._observers = []
        self._observers.extend([
            (nc, nc.addObserver_selector_name_object_(
                self, "scriptDidReload:", 
                "ScriptDidReloadNotification", 
                None
            ))
        ])

    def scriptDidReload_(self, notification):
        """Restore connections after script reload"""
        self.restoreConnections()
        self.updateInterface()

    @objc.python_method
    def restoreConnections(self):
        """Restore delegate connections for all rows"""
        for row in self.rows.values():
            if row and row.control:  # Safety check for valid objects
                row.delegate = self
                if row.type is TEXT:
                    row.control.setDelegate_(row)

    def shutdown(self):
        # Clean up notification observers
        if hasattr(self, '_observers'):
            nc = NSNotificationCenter.defaultCenter()
            for observer in self._observers:
                nc.removeObserver_(observer)
            self._observers = []
        
        # Clean up UI elements
        if hasattr(self, 'panel'):
            self.panel.close()
        
        if hasattr(self, 'rows'):
            for row in self.rows.values():
                if row and row.control:
                    row.delegate = None
                    if row.type is TEXT:
                        row.control.setDelegate_(None)
            self.rows.clear()

    def setVariable_to_(self, name, val):
        # Add safety check for variable existence
        if name not in self.script.vm.params:
            NSLog("Variable %s no longer exists", name)
            return

        var = self.script.vm.params[name]
        old_val = var.value  # Track old value
        var.value = val
        
        # Only run script if value actually changed and not animating
        if old_val != val and self.script.animationTimer is None:
            self.script.runScript()

    def callHandler_(self, name):
        var = self.script.vm.params[name]
        result = self.script.vm.call(var.name)
        self.script.echo(result.output)
        if result.ok:
            try:
                self.script.currentView.setCanvas(self.script.vm.canvas)
            except DeviceError as e:
                return self.script.crash()

    @objc.python_method
    def updateInterface(self):
        params = self.script.vm.params
        
        # Remove old variable widgets
        for name, widget in list(self.rows.items()):
            if name not in params:
                widget.removeFromSuperview()

        # Update existing and add new variables
        new_rows = OrderedDict()
        for name, var in params.items():
            row = self.rows.get(name)
            if row is None:
                row = DashboardRow.alloc().initWithVariable_forDelegate_(var, self)
                self.panel.contentView().addSubview_(row)
            else:
                row.updateConfig(var)
            new_rows[name] = row
        self.rows = new_rows

        if not self.rows:
            self.panel.orderOut_(None)
            return

        # Set the title of the parameter panel
        self.panel.setTitle_(self.script.window().title())

        # Calculate panel dimensions using DashboardRow constants
        label_width = max(row.label_w for row in self.rows.values())
        button_width = max(row.button_w for row in self.rows.values())
        number_width = max((row.num_w for row in self.rows.values() if row.type is NUMBER), default=0)
        
        # Calculate total heights and widths
        total_height = (len(self.rows) * DashboardRow.ROW_HEIGHT) + self.PANEL_TOP_PADDING + self.PANEL_BOTTOM_PADDING
        control_width = max(button_width, self.MIN_CONTROL_WIDTH)
        total_width = (
            label_width + 
            DashboardRow.LABEL_PADDING + 
            control_width
        )

        # Set panel constraints
        self.panel.setMinSize_((total_width, total_height))
        self.panel.setMaxSize_((total_width * self.MAX_WIDTH_MULTIPLIER, total_height))

        # Get current panel frame and calculate new position
        current_frame = self.panel.frame()
        
        # If panel hasn't been positioned yet (origin is 0,0)
        if current_frame.origin.x == 0 and current_frame.origin.y == 0:
            win = self.script.window().frame()
            screen = self.script.window().screen().visibleFrame()
            
            # Try to position to right of window
            if win.origin.x + win.size.width + total_width < screen.size.width:
                pOrigin = (win.origin.x + win.size.width, 
                          win.origin.y + win.size.height - total_height - self.TITLE_BAR_HEIGHT)
            # Try to position to left of window
            elif win.origin.x - total_width > 0:
                pOrigin = (win.origin.x - total_width, 
                          win.origin.y + win.size.height - total_height - self.TITLE_BAR_HEIGHT)
            # Fall back to overlapping position
            else:
                pOrigin = (win.origin.x + win.size.width - total_width - DashboardRow.MARGIN_RIGHT,
                          win.origin.y + DashboardRow.MARGIN_LEFT)
        else:
            # Keep current position but adjust for height change
            pOrigin = current_frame.origin
            pOrigin.y -= total_height - current_frame.size.height

        self.panel.setFrame_display_animate_((pOrigin, (total_width, total_height)), True, True)

        # Update row layouts
        indent = label_width + DashboardRow.LABEL_PADDING
        for idx, row in enumerate(self.rows.values()):
            # Add top padding to initial offset for each row
            row_offset = self.PANEL_TOP_PADDING + (idx * DashboardRow.ROW_HEIGHT)
            row.updateLayout(indent, total_width - DashboardRow.MARGIN_RIGHT,
                    total_width, row_offset)

        self.panel.orderFront_(None)



from ..context import RGB, CMYK
class ExportSheet(NSObject):
    # the script whose doExportAsImage and doExportAsMovie methods will be called
    script = IBOutlet()

    # Image export settings
    imageAccessory = IBOutlet()
    imageFormat = IBOutlet()
    imageZoom = IBOutlet()
    imagePageCount = IBOutlet()
    imagePagination = IBOutlet()
    imageCMYK = IBOutlet()

    # Movie export settings
    movieAccessory = IBOutlet()
    movieFormat = IBOutlet()
    movieFrames = IBOutlet()
    movieFps = IBOutlet()
    movieLoop = IBOutlet()
    movieBitrate = IBOutlet()

    def awakeFromNib(self):
        self.formats = dict(image=(0, 'pdf', 0,0, 'png', 'jpg', 'heic', 'tiff', 'gif', 0,0, 'pdf', 'eps'), movie=('mov', 'mov', 'gif'))
        self.movie = dict(format='mov', first=1, last=150, fps=30, bitrate=1, loop=0, codec=0)
        self.image = dict(format='pdf', zoom=100, first=1, last=1, cmyk=False, single=True)
        self.last = None


    @objc.python_method
    def beginExport(self, kind):
        # configure the accessory controls
        if kind=='image':
            format = self.image['format']
            accessory = self.imageAccessory

            if self.image['single']:
                self.imageFormat.selectItemAtIndex_(1)
            else:
                format_idx = 2 + self.formats['image'][2:].index(self.image['format'])
                self.imageFormat.selectItemAtIndex_(format_idx)
            self.imagePageCount.setIntValue_(self.image['last'])

            self.updatePagination()
            self.updateColorMode()

        elif kind=='movie':
            format = self.movie['format']
            accessory = self.movieAccessory
            format_idx = self.formats['movie'].index(self.movie['format'])
            should_loop = self.movie['format']=='gif' and self.movie['loop']==-1
            self.movieFrames.setIntValue_(self.movie['last'])
            self.movieFps.setIntValue_(self.movie['fps'])
            self.movieFormat.selectItemAtIndex_(format_idx)
            self.movieLoop.setState_(NSOnState if should_loop else NSOffState)
            self.movieLoop.setEnabled_(format=='gif')
            self.movieBitrate.setEnabled_(format!='gif')
            self.movieBitrate.selectItemWithTag_(self.movie['bitrate'])

        # set the default filename and save dir
        # path = self.script.fileName()
        path = self.script.path
        if path:
            dirName, fileName = os.path.split(path)
            fileName, ext = os.path.splitext(fileName)
            fileName += "." + format
        else:
            dirName, fileName = None, "Untitled.%s"%format

        # If a file was already exported, use that folder/filename as the default.
        if self.last is not None:
            dirName, fileName = self.last
            fileName, ext = os.path.splitext(fileName)

        # create the sheet
        exportPanel = NSSavePanel.savePanel()
        exportPanel.setNameFieldLabel_("Export To:")
        exportPanel.setPrompt_("Export")
        exportPanel.setCanSelectHiddenExtension_(True)
        exportPanel.setShowsTagField_(False)
        exportPanel.setAllowedFileTypes_([format])
        exportPanel.setAccessoryView_(accessory)
        self.exportPanel = exportPanel

        # present the dialog
        callback = "exportPanelDidEnd:returnCode:contextInfo:"
        context = 0 if kind=='image' else 1
        exportPanel.beginSheetForDirectory_file_modalForWindow_modalDelegate_didEndSelector_contextInfo_(
            dirName, fileName, NSApp().mainWindow(), self, callback, context
        )

    def exportPanelDidEnd_returnCode_contextInfo_(self, panel, returnCode, context):
        fname = panel.filename()
        panel.close()
        panel.setAccessoryView_(None)

        # if the user clicked Save:
        if returnCode:
            if context:
                kind, opts = 'movie', self.movieState()
            else:
                kind, opts = 'image', self.imageState()
            setattr(self, kind, dict(opts))  # save the options for next time
            self.last = os.path.split(fname) # save the path we exported to
            self.script.exportInit(kind, fname, opts)

    def movieState(self, key=None):
        fmts = self.formats['movie']
        fmt_idx = self.movieFormat.indexOfSelectedItem()
        state = dict(format = fmts[fmt_idx],
                     first=1,
                     last=self.movieFrames.intValue(),
                     fps=self.movieFps.floatValue(),
                     loop=-1 if self.movieLoop.state()==NSOnState else 0,
                     bitrate=self.movieBitrate.selectedItem().tag(),
                     codec=fmt_idx ) # 0=h265 1=h264
        if key:
            return state[key]
        return state

    def imageState(self, key=None):
        fmts = self.formats['image']
        fmt_idx = self.imageFormat.indexOfSelectedItem()
        state = dict(format=fmts[fmt_idx],
                     zoom=self.image['zoom'] / 100,
                     first=1,
                     cmyk=self.imageCMYK.state()==NSOnState,
                     single=fmt_idx==1,
                     last=self.imagePageCount.intValue())
        if key:
            return state[key]
        return state

    def updatePagination(self):
        label = 'Pages:' if self.imageState('single') else 'Files:'
        self.imagePagination.setStringValue_(label)

    def updateColorMode(self):
        format = self.imageState('format')
        can_cmyk = format in ('pdf','eps','tiff','jpg')
        self.imageCMYK.setEnabled_(can_cmyk)
        if not can_cmyk:
            self.imageCMYK.setState_(NSOffState)

    @IBAction
    def imageFormatChanged_(self, sender):
        format = self.formats['image'][sender.indexOfSelectedItem()]
        self.exportPanel.setAllowedFileTypes_([format])
        self.updateColorMode()
        self.updatePagination()

    @IBAction
    def imageZoomStepped_(self, sender):
        step = sender.intValue()
        sender.setIntValue_(0)

        self.imageZoomChanged_(None) # reflect any editing in text field
        pct = self.image['zoom']

        if step > 0:
            pct = 100 * ceil((pct + 1) / 100)
        elif step < 0:
            pct = 100 * floor((pct - 1) / 100)

        if 0 < pct < 10000:
            self.image['zoom'] = pct
            self.imageZoom.setStringValue_("%i%%" % pct)

    @IBAction
    def imageZoomChanged_(self, sender):
        pct = self.imageZoom.intValue()
        if pct > 0:
            self.image['zoom'] = pct
        else:
            pct = self.image['zoom']
        self.imageZoom.setStringValue_("%i%%" % pct)

    @IBAction
    def movieFormatChanged_(self, sender):
        format = self.formats['movie'][sender.indexOfSelectedItem()]
        self.exportPanel.setAllowedFileTypes_([format])
        is_gif = format=='gif'
        self.movieLoop.setState_(NSOnState if is_gif else NSOffState)
        self.movieLoop.setEnabled_(is_gif)
        self.movieBitrate.setEnabled_(not is_gif)

