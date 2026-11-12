import AppKit
import ApplicationServices
import CoreGraphics
import Foundation
import Network

private let hold: TimeInterval = 0.9
private let port: NWEndpoint.Port = 8766

final class PetApp: NSObject, NSApplicationDelegate {
    let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 340, height: 460),
        styleMask: [.borderless],
        backing: .buffered,
        defer: false
    )
    let view = PetView(frame: NSRect(x: 0, y: 0, width: 340, height: 460))
    var pose = "idle"
    var facing = "front"
    var until = Date.distantPast
    var listener: NWListener?
    var tap: CFMachPort?
    var monitors: [Any] = []
    var keyCount = 0
    var mouseCount = 0

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let saved = UserDefaults.standard.string(forKey: "awesome-desktop.facing"), saved == "back" {
            facing = "back"
        }
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 800, height: 600)
        window.setFrameOrigin(NSPoint(x: screen.maxX - 360, y: screen.minY + 24))
        window.isOpaque = false
        window.backgroundColor = .clear
        window.level = .floating
        window.ignoresMouseEvents = false
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        restoreFrame()
        view.autoresizingMask = [.width, .height]
        window.hasShadow = false
        view.pet = self
        window.contentView = view
        window.orderFrontRegardless()

        Timer.scheduledTimer(withTimeInterval: 1.0 / 12.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            if self.keyCount == 0, self.mouseCount == 0, self.pose != "idle", Date() >= self.until {
                self.pose = "idle"
            }
            self.view.needsDisplay = true
        }
        requestAccess()
        installTap()
        installMonitors()
        installServer()
    }

    func restoreFrame() {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: "pet.w") != nil else { return }
        let frame = NSRect(
            x: defaults.double(forKey: "pet.x"),
            y: defaults.double(forKey: "pet.y"),
            width: defaults.double(forKey: "pet.w"),
            height: defaults.double(forKey: "pet.h")
        )
        if frame.width > 80, frame.height > 80 {
            window.setFrame(frame, display: true)
            view.frame = NSRect(origin: .zero, size: frame.size)
        }
    }

    func saveFrame() {
        let frame = window.frame
        let defaults = UserDefaults.standard
        defaults.set(Double(frame.origin.x), forKey: "pet.x")
        defaults.set(Double(frame.origin.y), forKey: "pet.y")
        defaults.set(Double(frame.width), forKey: "pet.w")
        defaults.set(Double(frame.height), forKey: "pet.h")
    }

    func noteKey(down: Bool, code: Int64) {
        if code == 111 {
            if down { act(facing == "front" ? "back" : "front") }
            return
        }
        if down { keyCount += 1 } else { keyCount = max(0, keyCount - 1) }
        followHands()
    }

    func noteMouse(down: Bool) {
        if down { mouseCount += 1 } else { mouseCount = max(0, mouseCount - 1) }
        followHands()
    }

    func followHands() {
        if mouseCount > 0 {
            pose = "click"
            until = Date.distantFuture
        } else if keyCount > 0 {
            pose = "type"
            until = Date.distantFuture
        } else {
            until = Date().addingTimeInterval(0.2)
        }
        view.needsDisplay = true
    }

    func requestAccess() {
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let options = [key: true] as CFDictionary
        if !AXIsProcessTrustedWithOptions(options) {
            fputs("要跟着真实键盘和鼠标，请在弹出的辅助功能设置里允许 MirrorPet。\n", stderr)
        }
    }

    func act(_ name: String) {
        if name == "front" || name == "back" {
            facing = name
            UserDefaults.standard.set(name, forKey: "awesome-desktop.facing")
        } else if name == "type" || name == "click" {
            pose = name
            until = Date().addingTimeInterval(hold)
        } else if name == "idle" {
            pose = "idle"
        } else {
            return
        }
        view.needsDisplay = true
    }

    func installTap() {
        let mask = CGEventMask(1 << CGEventType.keyDown.rawValue)
            | CGEventMask(1 << CGEventType.keyUp.rawValue)
            | CGEventMask(1 << CGEventType.leftMouseDown.rawValue)
            | CGEventMask(1 << CGEventType.leftMouseUp.rawValue)
            | CGEventMask(1 << CGEventType.rightMouseDown.rawValue)
            | CGEventMask(1 << CGEventType.rightMouseUp.rawValue)
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: mask,
            callback: { _, type, event, _ in
                if type == .keyDown {
                    PetBox.shared?.noteKey(down: true, code: event.getIntegerValueField(.keyboardEventKeycode))
                } else if type == .keyUp {
                    PetBox.shared?.noteKey(down: false, code: event.getIntegerValueField(.keyboardEventKeycode))
                } else if type == .leftMouseDown || type == .rightMouseDown {
                    PetBox.shared?.noteMouse(down: true)
                } else if type == .leftMouseUp || type == .rightMouseUp {
                    PetBox.shared?.noteMouse(down: false)
                }
                return Unmanaged.passUnretained(event)
            },
            userInfo: nil
        ) else {
            fputs("还不能跟着真实键盘和鼠标。请到「系统设置 → 隐私与安全性 → 辅助功能」，允许启动这个小人的终端。\n", stderr)
            return
        }
        self.tap = tap
        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
    }

    func installMonitors() {
        let down = NSEvent.addGlobalMonitorForEvents(matching: [.keyDown, .leftMouseDown, .rightMouseDown]) { event in
            if event.type == .keyDown {
                PetBox.shared?.noteKey(down: true, code: Int64(event.keyCode))
            } else {
                PetBox.shared?.noteMouse(down: true)
            }
        }
        let up = NSEvent.addGlobalMonitorForEvents(matching: [.keyUp, .leftMouseUp, .rightMouseUp]) { event in
            if event.type == .keyUp {
                PetBox.shared?.noteKey(down: false, code: Int64(event.keyCode))
            } else {
                PetBox.shared?.noteMouse(down: false)
            }
        }
        if let down { monitors.append(down) }
        if let up { monitors.append(up) }
    }

    func installServer() {
        do {
            let listener = try NWListener(using: .tcp, on: port)
            listener.newConnectionHandler = { connection in
                connection.start(queue: .main)
                self.receive(connection)
            }
            listener.start(queue: .main)
            self.listener = listener
        } catch {
            fputs("8766 端口没有打开：\(error)\n", stderr)
        }
    }

    func receive(_ connection: NWConnection) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 512) { data, _, _, _ in
            if let data, let text = String(data: data, encoding: .utf8) {
                for line in text.split(whereSeparator: \.isNewline) {
                    self.act(String(line).trimmingCharacters(in: .whitespaces))
                }
            }
            connection.cancel()
        }
    }
}

private enum PetBox {
    static weak var shared: PetApp?
}

final class PetView: NSView {
    weak var pet: PetApp?
    let cutout: NSImage?
    let sprites: [String: NSImage]
    let hair: NSColor
    let skinColor: NSColor
    let stripe: NSColor

    override init(frame frameRect: NSRect) {
        let root = CommandLine.arguments.dropFirst().first.map { URL(fileURLWithPath: $0) }
        var loaded: [String: NSImage] = [:]
        if let root {
            let dir = root.appendingPathComponent("pet/skins/local")
            for name in ["front-idle", "front-type", "front-click", "back-idle", "back-type", "back-click"] {
                let jpg = dir.appendingPathComponent(name + ".jpg")
                let png = dir.appendingPathComponent(name + ".png")
                let file = FileManager.default.fileExists(atPath: jpg.path) ? jpg : png
                if let source = NSImage(contentsOf: file), let keyed = PetView.chromaGreen(source) {
                    loaded[name] = keyed
                }
            }
        }
        sprites = loaded
        let file = root?.appendingPathComponent("pet/skins/local/figure.png")
        if let file, let source = NSImage(contentsOf: file) {
            let made = PetView.removeBackground(source)
            cutout = made.image
            hair = made.hair
            skinColor = made.skin
            stripe = made.stripe
        } else {
            cutout = nil
            hair = NSColor(calibratedRed: 0.98, green: 0.84, blue: 0.22, alpha: 1)
            skinColor = NSColor(calibratedRed: 0.98, green: 0.74, blue: 0.70, alpha: 1)
            stripe = NSColor(calibratedRed: 0.75, green: 0.86, blue: 0.93, alpha: 1)
        }
        super.init(frame: frameRect)
    }

    required init?(coder: NSCoder) { nil }

    override var isOpaque: Bool { false }
    private var dragStart = NSPoint.zero
    private var frameStart = NSRect.zero

    override func mouseDown(with event: NSEvent) {
        dragStart = NSEvent.mouseLocation
        frameStart = window?.frame ?? .zero
    }

    override func mouseDragged(with event: NSEvent) {
        let now = NSEvent.mouseLocation
        window?.setFrameOrigin(NSPoint(x: frameStart.origin.x + now.x - dragStart.x, y: frameStart.origin.y + now.y - dragStart.y))
    }

    override func mouseUp(with event: NSEvent) {
        pet?.saveFrame()
    }

    override func scrollWheel(with event: NSEvent) {
        guard let window else { return }
        let scale = event.deltaY == 0 ? 1 : (event.deltaY > 0 ? 1.08 : 0.92)
        var frame = window.frame
        let width = min(980, max(150, frame.width * scale))
        let height = width * frame.height / frame.width
        let center = NSPoint(x: frame.midX, y: frame.midY)
        frame.size = NSSize(width: width, height: height)
        frame.origin = NSPoint(x: center.x - width / 2, y: center.y - height / 2)
        window.setFrame(frame, display: true)
        pet?.saveFrame()
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill()
        dirtyRect.fill()
        let pose = pet?.pose ?? "idle"
        let facing = pet?.facing ?? "front"
        let frame = Int(Date().timeIntervalSinceReferenceDate * 12)
        let action = (pose == "type" || pose == "click") ? pose : "idle"
        if let sprite = sprites["\(facing)-\(action)"] {
            let bump: CGFloat = pose == "type" ? (frame % 2 == 0 ? 0 : -14) : (pose == "click" ? (frame % 2 == 0 ? 0 : -10) : 0)
            sprite.draw(in: bounds.insetBy(dx: 6, dy: 6).offsetBy(dx: 0, dy: bump), from: .zero, operation: .sourceOver, fraction: 1)
            return
        }
        if facing == "back" {
            drawBack(pose: pose, frame: frame)
        } else if cutout != nil {
            drawFront(pose: pose, frame: frame)
        } else {
            drawFallback(pose: pose, frame: frame)
        }
    }

    func drawFront(pose: String, frame: Int) {
        guard let cutout else { return }
        let person = NSRect(x: 20, y: 70, width: 300, height: 340)
        cutout.draw(in: person, from: .zero, operation: .sourceOver, fraction: 1)
        drawDesk(NSRect(x: 24, y: 18, width: 292, height: 72))
        let beat = frame % 2 == 0
        drawKeyboard(NSRect(x: 58, y: 32, width: 150, height: 36), pressLeft: pose == "type" && beat, pressRight: pose == "type" && !beat)
        drawMouse(NSRect(x: 230, y: 36, width: 48, height: 32), down: pose == "click" && beat)
        if pose == "type" || pose == "click" {
            let shoulderY = person.minY + person.height * 0.30
            let leftFrom = NSPoint(x: person.midX - 36, y: shoulderY)
            let rightFrom = NSPoint(x: person.midX + 36, y: shoulderY)
            if pose == "click" {
                limb(leftFrom, NSPoint(x: 120, y: 100))
                limb(rightFrom, NSPoint(x: 252, y: beat ? 44 : 60))
            } else {
                limb(leftFrom, NSPoint(x: beat ? 78 : 110, y: beat ? 42 : 68))
                limb(rightFrom, NSPoint(x: beat ? 170 : 198, y: beat ? 68 : 42))
            }
        }
    }

    func drawBack(pose: String, frame: Int) {
        let beat = frame % 2 == 0
        fill(NSRect(x: 36, y: 250, width: 268, height: 150), radius: 12, color: NSColor(calibratedWhite: 0.93, alpha: 1))
        fill(NSRect(x: 52, y: 292, width: 236, height: 78), radius: 6, color: NSColor(calibratedRed: 0.16, green: 0.22, blue: 0.18, alpha: 1))
        drawDesk(NSRect(x: 28, y: 188, width: 284, height: 70))
        drawKeyboard(NSRect(x: 70, y: 206, width: 140, height: 32), pressLeft: pose == "type" && beat, pressRight: pose == "type" && !beat)
        drawMouse(NSRect(x: 224, y: 208, width: 44, height: 28), down: pose == "click" && beat)

        stripeDress(NSRect(x: 128, y: 78, width: 84, height: 130))
        pigtail(NSRect(x: 78, y: 168, width: 52, height: 36))
        pigtail(NSRect(x: 210, y: 168, width: 52, height: 36))
        fillOval(NSRect(x: 108, y: 176, width: 124, height: 118), color: hair)
        outlineOval(NSRect(x: 108, y: 176, width: 124, height: 118))

        let leftFrom = NSPoint(x: 142, y: 176)
        let rightFrom = NSPoint(x: 198, y: 176)
        if pose == "click" {
            limb(leftFrom, NSPoint(x: 150, y: 214))
            limb(rightFrom, NSPoint(x: 240, y: beat ? 214 : 228))
        } else if pose == "type" {
            limb(leftFrom, NSPoint(x: beat ? 92 : 118, y: beat ? 214 : 230))
            limb(rightFrom, NSPoint(x: beat ? 176 : 198, y: beat ? 230 : 214))
        } else {
            limb(leftFrom, NSPoint(x: 126, y: 168))
            limb(rightFrom, NSPoint(x: 214, y: 168))
        }
    }

    func drawFallback(pose: String, frame: Int) {
        drawFrontShape(pose: pose, frame: frame)
    }

    func drawFrontShape(pose: String, frame: Int) {
        let beat = frame % 2 == 0
        stripeDress(NSRect(x: 138, y: 120, width: 64, height: 70))
        fillOval(NSRect(x: 96, y: 176, width: 148, height: 140), color: skinColor)
        outlineOval(NSRect(x: 96, y: 176, width: 148, height: 140))
        pigtail(NSRect(x: 62, y: 210, width: 48, height: 34))
        pigtail(NSRect(x: 230, y: 210, width: 48, height: 34))
        drawDesk(NSRect(x: 24, y: 18, width: 292, height: 78))
        drawKeyboard(NSRect(x: 58, y: 36, width: 150, height: 36), pressLeft: pose == "type" && beat, pressRight: pose == "type" && !beat)
        drawMouse(NSRect(x: 230, y: 40, width: 48, height: 32), down: pose == "click" && beat)
    }

    func drawDesk(_ rect: NSRect) {
        fill(rect, radius: 10, color: NSColor(calibratedRed: 0.62, green: 0.40, blue: 0.22, alpha: 1))
        fill(NSRect(x: rect.minX, y: rect.maxY - 12, width: rect.width, height: 12), radius: 4, color: NSColor(calibratedRed: 0.45, green: 0.28, blue: 0.14, alpha: 1))
    }

    func drawKeyboard(_ rect: NSRect, pressLeft: Bool, pressRight: Bool) {
        fill(rect, radius: 5, color: NSColor(calibratedWhite: 0.16, alpha: 1))
        for row in 0..<2 {
            for col in 0..<6 {
                let down = (col < 3 && pressLeft) || (col >= 3 && pressRight)
                let key = NSRect(
                    x: rect.minX + 8 + CGFloat(col) * (rect.width - 16) / 6,
                    y: rect.minY + 6 + CGFloat(row) * 14 - (down ? 2 : 0),
                    width: (rect.width - 28) / 6,
                    height: 10
                )
                fill(key, radius: 2, color: down ? NSColor(calibratedRed: 0.95, green: 0.75, blue: 0.20, alpha: 1) : NSColor(calibratedWhite: 0.86, alpha: 1))
            }
        }
    }

    func drawMouse(_ rect: NSRect, down: Bool) {
        let body = NSRect(x: rect.minX, y: down ? rect.minY - 3 : rect.minY, width: rect.width, height: down ? rect.height - 4 : rect.height)
        fill(body, radius: 14, color: NSColor(calibratedWhite: 0.93, alpha: 1))
        fill(NSRect(x: body.midX - 8, y: body.maxY - (down ? 8 : 12), width: 16, height: down ? 5 : 8), radius: 3, color: down ? NSColor(calibratedRed: 0.95, green: 0.45, blue: 0.35, alpha: 1) : NSColor(calibratedWhite: 0.75, alpha: 1))
    }

    func limb(_ from: NSPoint, _ to: NSPoint) {
        let path = NSBezierPath()
        path.move(to: from)
        path.line(to: to)
        path.lineWidth = 20
        path.lineCapStyle = .round
        NSColor.black.setStroke()
        path.stroke()
        path.lineWidth = 14
        skinColor.setStroke()
        path.stroke()
        fillOval(NSRect(x: to.x - 11, y: to.y - 9, width: 22, height: 18), color: skinColor)
        outlineOval(NSRect(x: to.x - 11, y: to.y - 9, width: 22, height: 18))
    }

    func pigtail(_ rect: NSRect) {
        fillOval(rect, color: hair)
        outlineOval(rect)
    }

    func stripeDress(_ rect: NSRect) {
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(roundedRect: rect, xRadius: 16, yRadius: 16).addClip()
        var band = rect.minY
        var dark = true
        while band < rect.maxY {
            (dark ? NSColor.black : stripe).setFill()
            NSRect(x: rect.minX, y: band, width: rect.width, height: 10).fill()
            band += 10
            dark.toggle()
        }
        NSGraphicsContext.restoreGraphicsState()
        let edge = NSBezierPath(roundedRect: rect, xRadius: 16, yRadius: 16)
        edge.lineWidth = 3
        NSColor.black.setStroke()
        edge.stroke()
    }

    func fill(_ rect: NSRect, radius: CGFloat, color: NSColor) {
        color.setFill()
        NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
    }

    func fillOval(_ rect: NSRect, color: NSColor) {
        color.setFill()
        NSBezierPath(ovalIn: rect).fill()
    }

    func outlineOval(_ rect: NSRect) {
        let path = NSBezierPath(ovalIn: rect)
        path.lineWidth = 3
        NSColor.black.setStroke()
        path.stroke()
    }

    static func chromaGreen(_ image: NSImage) -> NSImage? {
        guard let tiff = image.tiffRepresentation, let source = NSBitmapImageRep(data: tiff) else { return nil }
        let width = source.pixelsWide
        let height = source.pixelsHigh
        guard let dest = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: width,
            pixelsHigh: height,
            bitsPerSample: 8,
            samplesPerPixel: 4,
            hasAlpha: true,
            isPlanar: false,
            colorSpaceName: .deviceRGB,
            bytesPerRow: width * 4,
            bitsPerPixel: 32
        ), let raw = dest.bitmapData else { return nil }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: dest)
        source.draw(in: NSRect(x: 0, y: 0, width: width, height: height))
        NSGraphicsContext.restoreGraphicsState()
        func offset(_ x: Int, _ y: Int) -> Int { (y * width + x) * 4 }
        func isGreen(_ i: Int) -> Bool {
            let r = Int(raw[i])
            let g = Int(raw[i + 1])
            let b = Int(raw[i + 2])
            return g > 90 && g > r + 28 && g > b + 28
        }
        for y in 0..<height {
            for x in 0..<width {
                let i = offset(x, y)
                if isGreen(i) {
                    raw[i] = 0
                    raw[i + 1] = 0
                    raw[i + 2] = 0
                    raw[i + 3] = 0
                } else {
                    raw[i + 3] = 255
                }
            }
        }
        for _ in 0..<3 {
            var fringe: [Int] = []
            for y in 0..<height {
                for x in 0..<width {
                    let i = offset(x, y)
                    if raw[i + 3] == 0 { continue }
                    let g = Int(raw[i + 1])
                    guard g > Int(raw[i]) && g > Int(raw[i + 2]) else { continue }
                    for neighbor in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)] {
                        if neighbor.0 < 0 || neighbor.1 < 0 || neighbor.0 >= width || neighbor.1 >= height
                            || raw[offset(neighbor.0, neighbor.1) + 3] == 0 {
                            fringe.append(i)
                            break
                        }
                    }
                }
            }
            for i in fringe {
                raw[i] = 0
                raw[i + 1] = 0
                raw[i + 2] = 0
                raw[i + 3] = 0
            }
        }
        let result = NSImage(size: NSSize(width: width, height: height))
        result.addRepresentation(dest)
        return result
    }

    static func removeBackground(_ image: NSImage) -> (image: NSImage, hair: NSColor, skin: NSColor, stripe: NSColor) {
        let fallbackHair = NSColor(calibratedRed: 0.98, green: 0.84, blue: 0.22, alpha: 1)
        let fallbackSkin = NSColor(calibratedRed: 0.98, green: 0.74, blue: 0.70, alpha: 1)
        let fallbackStripe = NSColor(calibratedRed: 0.75, green: 0.86, blue: 0.93, alpha: 1)
        guard let tiff = image.tiffRepresentation, let source = NSBitmapImageRep(data: tiff) else {
            return (image, fallbackHair, fallbackSkin, fallbackStripe)
        }
        let width = source.pixelsWide
        let height = source.pixelsHigh
        guard width > 4, height > 4,
              let dest = NSBitmapImageRep(
                bitmapDataPlanes: nil,
                pixelsWide: width,
                pixelsHigh: height,
                bitsPerSample: 8,
                samplesPerPixel: 4,
                hasAlpha: true,
                isPlanar: false,
                colorSpaceName: .deviceRGB,
                bytesPerRow: width * 4,
                bitsPerPixel: 32
              ),
              let raw = dest.bitmapData
        else {
            return (image, fallbackHair, fallbackSkin, fallbackStripe)
        }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: dest)
        source.draw(in: NSRect(x: 0, y: 0, width: width, height: height))
        NSGraphicsContext.restoreGraphicsState()

        func offset(_ x: Int, _ y: Int) -> Int { (y * width + x) * 4 }
        func sample(_ x: Int, _ y: Int) -> (Int, Int, Int) {
            let i = offset(x, y)
            return (Int(raw[i]), Int(raw[i + 1]), Int(raw[i + 2]))
        }
        let corners = [sample(2, 2), sample(width - 3, 2), sample(2, height - 3), sample(width - 3, height - 3)]
        let base = (
            corners.map(\.0).reduce(0, +) / 4,
            corners.map(\.1).reduce(0, +) / 4,
            corners.map(\.2).reduce(0, +) / 4
        )
        func near(_ x: Int, _ y: Int) -> Bool {
            let pixel = sample(x, y)
            let dr = pixel.0 - base.0
            let dg = pixel.1 - base.1
            let db = pixel.2 - base.2
            return dr * dr + dg * dg + db * db < 58 * 58
        }
        var seen = [UInt8](repeating: 0, count: width * height)
        var stack: [(Int, Int)] = []
        for x in 0..<width {
            stack.append((x, 0))
            stack.append((x, height - 1))
        }
        for y in 0..<height {
            stack.append((0, y))
            stack.append((width - 1, y))
        }
        while let point = stack.popLast() {
            let x = point.0
            let y = point.1
            if x < 0 || y < 0 || x >= width || y >= height { continue }
            let mark = y * width + x
            if seen[mark] == 1 { continue }
            seen[mark] = 1
            if !near(x, y) { continue }
            let i = offset(x, y)
            raw[i] = 0
            raw[i + 1] = 0
            raw[i + 2] = 0
            raw[i + 3] = 0
            stack.append((x + 1, y))
            stack.append((x - 1, y))
            stack.append((x, y + 1))
            stack.append((x, y - 1))
        }
        for _ in 0..<8 {
            var erase: [Int] = []
            for y in 0..<height {
                for x in 0..<width {
                    let i = offset(x, y)
                    if raw[i + 3] == 0 { continue }
                    let pixel = sample(x, y)
                    let dr = pixel.0 - base.0
                    let dg = pixel.1 - base.1
                    let db = pixel.2 - base.2
                    let likeWall = dr * dr + dg * dg + db * db < 58 * 58
                    let dark = pixel.0 + pixel.1 + pixel.2 < 90
                    var touchesClear = false
                    for neighbor in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)] {
                        if neighbor.0 < 0 || neighbor.1 < 0 || neighbor.0 >= width || neighbor.1 >= height {
                            touchesClear = true
                            break
                        }
                        if raw[offset(neighbor.0, neighbor.1) + 3] == 0 {
                            touchesClear = true
                            break
                        }
                    }
                    if likeWall || (dark && touchesClear) {
                        erase.append(i)
                    }
                }
            }
            if erase.isEmpty { break }
            for i in erase {
                raw[i] = 0
                raw[i + 1] = 0
                raw[i + 2] = 0
                raw[i + 3] = 0
            }
        }

        var hairSum = (0, 0, 0, 0)
        var skinSum = (0, 0, 0, 0)
        var stripeSum = (0, 0, 0, 0)
        for y in stride(from: 0, to: height, by: 4) {
            for x in stride(from: 0, to: width, by: 4) {
                let i = offset(x, y)
                if raw[i + 3] < 200 { continue }
                let r = Int(raw[i])
                let g = Int(raw[i + 1])
                let b = Int(raw[i + 2])
                if r > 190 && g > 150 && b < 130 {
                    hairSum.0 += r; hairSum.1 += g; hairSum.2 += b; hairSum.3 += 1
                } else if r > 190 && g > 120 && b > 120 && r > b {
                    skinSum.0 += r; skinSum.1 += g; skinSum.2 += b; skinSum.3 += 1
                } else if b > r + 15 && g > 120 && r > 80 {
                    stripeSum.0 += r; stripeSum.1 += g; stripeSum.2 += b; stripeSum.3 += 1
                }
            }
        }
        func tone(_ sum: (Int, Int, Int, Int), _ fallback: NSColor) -> NSColor {
            guard sum.3 > 8 else { return fallback }
            return NSColor(calibratedRed: CGFloat(sum.0) / CGFloat(sum.3) / 255,
                           green: CGFloat(sum.1) / CGFloat(sum.3) / 255,
                           blue: CGFloat(sum.2) / CGFloat(sum.3) / 255,
                           alpha: 1)
        }
        let result = NSImage(size: NSSize(width: width, height: height))
        result.addRepresentation(dest)
        return (result, tone(hairSum, fallbackHair), tone(skinSum, fallbackSkin), tone(stripeSum, fallbackStripe))
    }
}

let app = NSApplication.shared
let delegate = PetApp()
PetBox.shared = delegate
app.setActivationPolicy(.accessory)
app.delegate = delegate
app.run()
