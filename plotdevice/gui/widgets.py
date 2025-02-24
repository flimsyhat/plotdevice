# encoding: utf-8
import os, re
from collections import OrderedDict
from ..lib.cocoa import *
from math import floor, ceil
import objc
from ..gfx.colors import Color
from ..gfx.atoms import COLOR, NUMBER, TEXT, BOOLEAN, BUTTON, SELECT

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
    # Layout constants
    MARGIN_LEFT = 10
    MARGIN_RIGHT = 10
    ROW_HEIGHT = 30
    LABEL_HEIGHT = 18
    CONTROL_HEIGHT = 23
    LABEL_PADDING = 15  # Space between label and control

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

            num = NSTextField.alloc().init()
            num.setBordered_(False)
            num.setEditable_(False)
            num.setAutoresizingMask_(NSViewMinXMargin)
            num.setSelectable_(True)
            num.setDrawsBackground_(False)
            num.setFont_(SMALL_FONT)

            # measure all the possible values to decide on the text-field width
            num_w = self._num_w(var.min, var.max, var.step)
            num.setStringValue_(self._fmt(var.value))
            num.setFrameSize_((num_w, 18))
            self.addSubview_(num)
            self.step = var.step
            self.num = num

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

        self.name = var.name
        self.type = var.type
        self.label = label
        self.control = control
        self.button_w = control.frame().size.width if var.type is BUTTON else 0
        self.num_w = num_w if var.type is NUMBER else 0
        self.label_w = label.frame().size.width
        self.delegate = delegate
        return self

    @objc.python_method
    def _fmt(self, num):
        s = "{:,.3f}".format(num)
        s = re.sub(r'\.0+$', '', s)
        return re.sub(r'(\.[^0])+0*$', r'\1', s)

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
            self.num_w = self._num_w(var.min, var.max, var.step)
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

    @objc.python_method
    def updateLayout(self, indent, width, row_width, offset):
        # Base row frame
        self.setFrame_(((0, offset), (row_width, self.ROW_HEIGHT)))
        
        # Center label vertically - use actual label height for perfect centering
        label_height = self.label.frame().size.height  # Get actual height instead of LABEL_HEIGHT
        label_y = (self.ROW_HEIGHT - label_height) / 2
        control_y = (self.ROW_HEIGHT - self.CONTROL_HEIGHT) / 2
        
        # Position label with right alignment
        self.label.setFrame_(((self.MARGIN_LEFT, label_y), 
                             (indent - self.LABEL_PADDING, label_height)))
        self.label.setAlignment_(NSRightTextAlignment)  # Ensure right alignment
        
        # Available width for controls
        control_width = width - indent - self.MARGIN_RIGHT
        
        # Position control based on type
        if self.type is TEXT:
            self.control.setFrame_(((indent, control_y), (control_width, self.CONTROL_HEIGHT)))
        elif self.type is BOOLEAN:
            self.control.setFrameOrigin_((indent, control_y))
        elif self.type is NUMBER:
            slider_width = control_width - self.num_w - 10
            self.control.setFrame_(((indent, control_y), (slider_width, self.CONTROL_HEIGHT)))
            self.num.setFrameOrigin_((indent + slider_width + 10, control_y))
        elif self.type is BUTTON:
            self.control.setFrameOrigin_((indent, control_y - 5))  # Buttons need slight adjustment
        elif self.type is COLOR:
            self.control.setFrame_(((indent, control_y), (44, self.CONTROL_HEIGHT)))
        elif self.type is SELECT:
            self.control.setFrame_(((indent, control_y), (control_width, self.CONTROL_HEIGHT)))

    def numberChanged_(self, sender):
        self.roundOff()
        if self.delegate:
            self.delegate.setVariable_to_(self.name, sender.floatValue())

    def controlTextDidChange_(self, note):
        if self.delegate:
            sender = note.object()
            self.delegate.setVariable_to_(self.name, sender.stringValue())

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

class DashboardController(NSObject):
    script = IBOutlet()
    panel = IBOutlet()

    def awakeFromNib(self):
        self.panel.contentView().setFlipped_(True)
        self.rows = OrderedDict()
        self.positioned = False
        
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
        
        # Remove old variables
        for name, widget in list(self.rows.items()):
            if name not in params:
                widget.removeFromSuperview()
                self.script.vm.namespace.pop(name, None)

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
        else:
            # Set the title of the parameter panel to the title of the window
            self.panel.setTitle_(self.script.window().title())

            # recalculate the layout
            (pOrigin, pSize) = self.panel.frame()
            label_w = max([v.label_w for v in self.rows.values()])
            button_w = max([v.button_w for v in self.rows.values()])
            num_w = max([v.num_w for v in self.rows.values()])
            ph = len(self.rows) * 30 + 30
            pw = label_w + 15 + max(button_w, 200) + num_w
            col = label_w + 15

            self.panel.setMinSize_( (pw, ph))
            self.panel.setMaxSize_( (pw * 5, ph))

            needs_resize = pSize.width < pw or pSize.height != ph
            pw = max(pw, pSize.width)

            if not self.positioned:
                win = self.script.window().frame()
                screen = self.script.window().screen().visibleFrame()
                if win.origin.x + win.size.width + pw < screen.size.width:
                    pOrigin = (win.origin.x + win.size.width, win.origin.y + win.size.height - ph - 38)
                elif win.origin.x - pw > 0:
                    pOrigin = (win.origin.x - pw, win.origin.y + win.size.height - ph - 38)
                else:
                    pOrigin = (win.origin.x + win.size.width - pw - 15, win.origin.y + 15)
                self.panel.setFrame_display_animate_( (pOrigin, (pw,ph)), True, True )
                self.positioned = True

            elif needs_resize:
                pOrigin.y -= ph-pSize.height
                self.panel.setFrame_display_animate_( (pOrigin, (pw,ph)), True, True )

            # reposition the elements of each row to fit the new panel size and row contents
            for idx, v in enumerate(self.rows.values()):
                v.updateLayout(col, pw - 10 - num_w, pw, idx*30)

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

