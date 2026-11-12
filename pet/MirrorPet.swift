import AppKit
import CoreGraphics
import Foundation
import Network

private let hold: TimeInterval = 0.22
private let port: NWEndpoint.Port = 8766

final class PetApp: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 220, height: 280),
        styleMask: [.borderless],
        backing: .buffered,
        defer: false
    )
    let view = PetView(frame: NSRect(x: 0, y: 0, width: 220, height: 280))
    var pose = "idle"
    var until = Date.distantPast
    var listener: NWListener?
    var tap: CFMachPort?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 800, height: 600)
        window.setFrameOrigin(NSPoint(x: screen.maxX - 240, y: screen.minY + 24))
        window.isOpaque = false
        window.backgroundColor = .clear
        window.level = .floating
        window.ignoresMouseEvents = true
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        window.hasShadow = false
        view.pet = self
        window.contentView = view
        window.orderFrontRegardless()

        Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            guard let self else { return }
            if self.pose != "idle", Date() >= self.until {
                self.act("idle")
            }
        }
        installTap()
        installServer()
    }

    func act(_ name: String) {
        let next: String
        if name == "type" || name == "click" {
            next = name
            until = Date().addingTimeInterval(hold)
        } else if name == "idle" {
            next = "idle"
        } else {
            return
        }
        pose = next
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
            fputs("还不能跟着真实键盘和鼠标。请到「系统设置 → 隐私与安全性 → 辅助功能」，允许启动这个小人的终端。命令 python3 -m pet act 不需要这个权限。\n", stderr)
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
    let photo: NSImage?

    override init(frame frameRect: NSRect) {
        let root = CommandLine.arguments.dropFirst().first.map { URL(fileURLWithPath: $0) }
        let file = root?.appendingPathComponent("pet/skins/local/figure.png")
        if let file, FileManager.default.fileExists(atPath: file.path) {
            photo = NSImage(contentsOf: file)
        } else {
            photo = nil
        }
        super.init(frame: frameRect)
    }

    required init?(coder: NSCoder) { nil }

    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill()
        dirtyRect.fill()
        let pose = pet?.pose ?? "idle"
        if let photo {
            let rect = NSRect(x: 24, y: 78, width: 172, height: 186)
            photo.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1)
        } else {
            drawPerson(pose)
        }
        drawProp(pose)
        let caption = pose == "type" ? "按键盘" : (pose == "click" ? "按鼠标" : "待命")
        let text = NSAttributedString(string: caption, attributes: [
            .font: NSFont.systemFont(ofSize: 13, weight: .medium),
            .foregroundColor: NSColor.white,
        ])
        text.draw(at: NSPoint(x: 78, y: 18))
    }

    func drawPerson(_ pose: String) {
        let body = NSColor(calibratedRed: 0.29, green: 0.45, blue: 0.78, alpha: 1)
        let skin = NSColor(calibratedRed: 0.96, green: 0.83, blue: 0.70, alpha: 1)
        NSColor(calibratedWhite: 0.12, alpha: 0.88).setFill()
        NSBezierPath(roundedRect: NSRect(x: 28, y: 46, width: 164, height: 28), xRadius: 6, yRadius: 6).fill()
        body.setFill()
        NSBezierPath(roundedRect: NSRect(x: 78, y: 78, width: 64, height: 70), xRadius: 16, yRadius: 16).fill()
        skin.setFill()
        NSBezierPath(ovalIn: NSRect(x: 80, y: 150, width: 60, height: 60)).fill()
        NSColor(calibratedWhite: 0.16, alpha: 1).setFill()
        NSBezierPath(ovalIn: NSRect(x: 96, y: 176, width: 8, height: 10)).fill()
        NSBezierPath(ovalIn: NSRect(x: 116, y: 176, width: 8, height: 10)).fill()
        let arm = pose == "idle" ? 96.0 : 62.0
        skin.setFill()
        NSBezierPath(roundedRect: NSRect(x: 58, y: arm, width: 22, height: 48), xRadius: 8, yRadius: 8).fill()
        NSBezierPath(roundedRect: NSRect(x: 140, y: arm, width: 22, height: 48), xRadius: 8, yRadius: 8).fill()
    }

    func drawProp(_ pose: String) {
        if pose == "type" {
            NSColor(calibratedWhite: 0.95, alpha: 1).setFill()
            NSBezierPath(roundedRect: NSRect(x: 48, y: 52, width: 124, height: 18), xRadius: 3, yRadius: 3).fill()
            NSColor(calibratedRed: 0.98, green: 0.78, blue: 0.18, alpha: 1).setFill()
            for index in 0..<6 {
                NSBezierPath(rect: NSRect(x: 56 + index * 18, y: 56, width: 12, height: 10)).fill()
            }
        } else if pose == "click" {
            NSColor.white.setFill()
            NSBezierPath(roundedRect: NSRect(x: 150, y: 50, width: 36, height: 22), xRadius: 8, yRadius: 8).fill()
            NSColor(calibratedRed: 0.20, green: 0.75, blue: 0.45, alpha: 1).setFill()
            NSBezierPath(ovalIn: NSRect(x: 160, y: 56, width: 10, height: 10)).fill()
        }
    }
}

let app = NSApplication.shared
let delegate = PetApp()
PetBox.shared = delegate
app.setActivationPolicy(.accessory)
app.delegate = delegate
app.run()
