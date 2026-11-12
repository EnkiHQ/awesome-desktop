import AppKit
import CoreGraphics
import Foundation
import Network

private let hold: TimeInterval = 0.9
private let port: NWEndpoint.Port = 8766

final class PetApp: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 300, height: 360),
        styleMask: [.borderless],
        backing: .buffered,
        defer: false
    )
    let view = PetView(frame: NSRect(x: 0, y: 0, width: 300, height: 360))
    var pose = "idle"
    var until = Date.distantPast
    var listener: NWListener?
    var tap: CFMachPort?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 800, height: 600)
        window.setFrameOrigin(NSPoint(x: screen.maxX - 320, y: screen.minY + 24))
        window.isOpaque = false
        window.backgroundColor = .clear
        window.level = .floating
        window.ignoresMouseEvents = true
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        window.hasShadow = false
        view.pet = self
        window.contentView = view
        window.orderFrontRegardless()

        Timer.scheduledTimer(withTimeInterval: 1.0 / 12.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            if self.pose != "idle", Date() >= self.until {
                self.pose = "idle"
            }
            self.view.needsDisplay = true
        }
        installTap()
        installServer()
    }

    func act(_ name: String) {
        if name == "type" || name == "click" {
            pose = name
            until = Date().addingTimeInterval(hold)
        } else if name == "idle" {
            pose = "idle"
        }
        view.needsDisplay = true
    }

    func installTap() {
        let mask = CGEventMask(1 << CGEventType.keyDown.rawValue)
            | CGEventMask(1 << CGEventType.leftMouseDown.rawValue)
            | CGEventMask(1 << CGEventType.rightMouseDown.rawValue)
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: mask,
            callback: { _, type, event, _ in
                if type == .keyDown {
                    PetBox.shared?.act("type")
                } else if type == .leftMouseDown || type == .rightMouseDown {
                    PetBox.shared?.act("click")
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

    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill()
        dirtyRect.fill()
        let pose = pet?.pose ?? "idle"
        let frame = Int(Date().timeIntervalSinceReferenceDate * 12)
        drawScene(pose: pose, frame: frame)
    }

    func drawScene(pose: String, frame: Int) {
        let typing = pose == "type"
        let clicking = pose == "click"
        let beat = frame % 4
        let pressLeft = typing && beat % 2 == 0
        let pressRight = typing && beat % 2 == 1
        let mouseDown = clicking && beat % 2 == 0
        let bob: CGFloat = typing ? CGFloat(beat % 2 == 0 ? 0 : -3) : (clicking && mouseDown ? -2 : 0)

        drawDesk()
        drawKeyboard(pressLeft: pressLeft, pressRight: pressRight)
        drawMouse(down: mouseDown)
        drawGirl(bob: bob, pose: pose, pressLeft: pressLeft, pressRight: pressRight, mouseDown: mouseDown, blink: !typing && !clicking && frame % 48 < 2)
    }

    func drawDesk() {
        fill(NSRect(x: 18, y: 28, width: 264, height: 58), radius: 10, color: wood)
        fill(NSRect(x: 18, y: 74, width: 264, height: 12), radius: 4, color: woodDark)
    }

    func drawKeyboard(pressLeft: Bool, pressRight: Bool) {
        fill(NSRect(x: 46, y: 46, width: 150, height: 34), radius: 5, color: NSColor(calibratedWhite: 0.16, alpha: 1))
        for row in 0..<2 {
            for col in 0..<7 {
                let down = (row == 1 && col < 3 && pressLeft) || (row == 1 && col >= 4 && pressRight)
                let key = NSRect(x: 54 + CGFloat(col) * 20, y: 52 + CGFloat(row) * 13 - (down ? 2 : 0), width: 15, height: 9)
                fill(key, radius: 2, color: down ? keyDown : keyUp)
            }
        }
    }

    func drawMouse(down: Bool) {
        let body = NSRect(x: 214, y: down ? 44 : 48, width: 40, height: down ? 26 : 30)
        fill(body, radius: 12, color: NSColor(calibratedWhite: 0.92, alpha: 1))
        let button = NSRect(x: 226, y: body.maxY - (down ? 8 : 12), width: 16, height: down ? 5 : 8)
        fill(button, radius: 3, color: down ? NSColor(calibratedRed: 0.95, green: 0.45, blue: 0.35, alpha: 1) : NSColor(calibratedWhite: 0.75, alpha: 1))
    }

    func drawGirl(bob: CGFloat, pose: String, pressLeft: Bool, pressRight: Bool, mouseDown: Bool, blink: Bool) {
        let y = bob
        stripeDress(NSRect(x: 118, y: 96 + y, width: 64, height: 58))
        limb(NSPoint(x: 128, y: 140 + y), NSPoint(x: handX(pose, left: true, press: pressLeft), y: handY(pose, left: true, press: pressLeft, mouseDown: mouseDown)), width: 16)
        limb(NSPoint(x: 172, y: 140 + y), NSPoint(x: handX(pose, left: false, press: pressRight), y: handY(pose, left: false, press: pressRight, mouseDown: mouseDown)), width: 16)
        pigtail(NSRect(x: 58, y: 176 + y, width: 46, height: 34))
        pigtail(NSRect(x: 196, y: 176 + y, width: 46, height: 34))
        fill(NSRect(x: 86, y: 156 + y, width: 128, height: 118), radius: 58, color: skin)
        outline(NSRect(x: 86, y: 156 + y, width: 128, height: 118), radius: 58)
        if blink {
            strokeLine(NSPoint(x: 112, y: 214 + y), NSPoint(x: 142, y: 214 + y), width: 5)
            strokeLine(NSPoint(x: 158, y: 214 + y), NSPoint(x: 188, y: 214 + y), width: 5)
        } else {
            eye(NSRect(x: 108, y: 196 + y, width: 38, height: 46))
            eye(NSRect(x: 154, y: 196 + y, width: 38, height: 46))
        }
        strokeLine(NSPoint(x: 138, y: 186 + y), NSPoint(x: 162, y: 186 + y), width: 3)
        let smile = NSBezierPath()
        smile.move(to: NSPoint(x: 136, y: 176 + y))
        smile.curve(to: NSPoint(x: 164, y: 176 + y), controlPoint1: NSPoint(x: 144, y: 168 + y), controlPoint2: NSPoint(x: 156, y: 168 + y))
        smile.lineWidth = 3
        smile.lineCapStyle = .round
        NSColor.black.setStroke()
        smile.stroke()
    }

    func handX(_ pose: String, left: Bool, press: Bool) -> CGFloat {
        if pose == "click" { return left ? 108 : 232 }
        if pose == "type" { return left ? (press ? 78 : 96) : (press ? 176 : 158) }
        return left ? 104 : 196
    }

    func handY(_ pose: String, left: Bool, press: Bool, mouseDown: Bool) -> CGFloat {
        if pose == "click" { return left ? 108 : (mouseDown ? 52 : 64) }
        if pose == "type" { return press ? 58 : 78 }
        return 112
    }

    func eye(_ rect: NSRect) {
        fillOval(rect, color: .white)
        outlineOval(rect)
        let iris = NSRect(x: rect.midX - 11, y: rect.minY + 8, width: 24, height: 28)
        fillOval(iris, color: irisBlue)
        fillOval(NSRect(x: iris.midX - 6, y: iris.minY + 6, width: 14, height: 16), color: .black)
        fillOval(NSRect(x: iris.minX + 4, y: iris.maxY - 12, width: 8, height: 8), color: .white)
    }

    func pigtail(_ rect: NSRect) {
        fillOval(rect, color: hair)
        outlineOval(rect)
        fillOval(NSRect(x: rect.midX - 7, y: rect.minY - 8, width: 14, height: 14), color: hair)
    }

    func stripeDress(_ rect: NSRect) {
        NSGraphicsContext.saveGraphicsState()
        let clip = NSBezierPath(roundedRect: rect, xRadius: 16, yRadius: 16)
        clip.addClip()
        var band = rect.minY
        var dark = true
        while band < rect.maxY {
            (dark ? NSColor.black : stripe).setFill()
            NSRect(x: rect.minX, y: band, width: rect.width, height: 9).fill()
            band += 9
            dark.toggle()
        }
        NSGraphicsContext.restoreGraphicsState()
        outline(rect, radius: 16)
    }

    func limb(_ from: NSPoint, _ to: NSPoint, width: CGFloat) {
        let path = NSBezierPath()
        path.move(to: from)
        path.line(to: to)
        path.lineWidth = width + 6
        path.lineCapStyle = .round
        NSColor.black.setStroke()
        path.stroke()
        path.lineWidth = width
        skin.setStroke()
        path.stroke()
        fillOval(NSRect(x: to.x - 11, y: to.y - 9, width: 22, height: 18), color: skin)
        outlineOval(NSRect(x: to.x - 11, y: to.y - 9, width: 22, height: 18))
    }

    func fill(_ rect: NSRect, radius: CGFloat, color: NSColor) {
        color.setFill()
        NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
    }

    func outline(_ rect: NSRect, radius: CGFloat) {
        let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
        path.lineWidth = 3
        NSColor.black.setStroke()
        path.stroke()
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

    func strokeLine(_ a: NSPoint, _ b: NSPoint, width: CGFloat) {
        let path = NSBezierPath()
        path.move(to: a)
        path.line(to: b)
        path.lineWidth = width
        path.lineCapStyle = .round
        NSColor.black.setStroke()
        path.stroke()
    }

    var skin: NSColor { NSColor(calibratedRed: 0.98, green: 0.74, blue: 0.70, alpha: 1) }
    var hair: NSColor { NSColor(calibratedRed: 0.98, green: 0.84, blue: 0.22, alpha: 1) }
    var irisBlue: NSColor { NSColor(calibratedRed: 0.62, green: 0.78, blue: 0.90, alpha: 1) }
    var stripe: NSColor { NSColor(calibratedRed: 0.75, green: 0.86, blue: 0.93, alpha: 1) }
    var wood: NSColor { NSColor(calibratedRed: 0.62, green: 0.40, blue: 0.22, alpha: 1) }
    var woodDark: NSColor { NSColor(calibratedRed: 0.45, green: 0.28, blue: 0.14, alpha: 1) }
    var keyUp: NSColor { NSColor(calibratedWhite: 0.86, alpha: 1) }
    var keyDown: NSColor { NSColor(calibratedRed: 0.95, green: 0.75, blue: 0.20, alpha: 1) }
}

let app = NSApplication.shared
let delegate = PetApp()
PetBox.shared = delegate
app.setActivationPolicy(.accessory)
app.delegate = delegate
app.run()
