import Foundation
import Network

/// Runs the bundled get.sh, which unpacks the bundled copy of this repository and runs scripts/install.sh.
enum Installer {
    static func makeProcess(token: String) -> Process? {
        guard let script = Bundle.main.url(forResource: "get", withExtension: "sh"),
              let payload = Bundle.main.url(forResource: "ai-api", withExtension: "tar.gz") else { return nil }
        var env: [String: String] = [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": ProcessInfo.processInfo.environment["HOME"] ?? NSHomeDirectory(),
            "LOCAL_AGENT_TARBALL": payload.absoluteString,
        ]
        if !token.isEmpty { env["LOCAL_AGENT_TOKEN"] = token }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = [script.path]
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        return p
    }
}

/// The first connection to a LAN address makes macOS ask for "local network" access in the app's name.
/// Ask it here, from the app itself, and keep retrying until the user answers.
enum Gateway {
    static let host = "10.80.118.138"
    static let port: UInt16 = 52440

    /// Calls `note` with progress text and `done(nil)` on success or `done(last error)` on timeout. `done` runs on the main queue.
    static func waitUntilReachable(timeout: TimeInterval = 120, note: @escaping (String) -> Void, done: @escaping (String?) -> Void) {
        let deadline = Date().addingTimeInterval(timeout)
        final class Progress: @unchecked Sendable {
            private let lock = NSLock()
            private var _error = "응답 없음", _announced = false
            var error: String { get { lock.withLock { _error } } set { lock.withLock { _error = newValue } } }
            /// True only the first time it is called.
            func announceOnce() -> Bool { lock.withLock { defer { _announced = true }; return !_announced } }
        }
        let progress = Progress()

        func attempt() {
            let conn = NWConnection(host: NWEndpoint.Host(host), port: NWEndpoint.Port(rawValue: port)!, using: .tcp)
            var finished = false
            func finish(_ reachable: Bool) {
                guard !finished else { return }
                finished = true
                conn.cancel()
                if reachable { DispatchQueue.main.async { done(nil) }; return }
                if Date() >= deadline { DispatchQueue.main.async { done(progress.error) }; return }
                DispatchQueue.global().asyncAfter(deadline: .now() + 2) { attempt() }
            }
            conn.stateUpdateHandler = { state in
                switch state {
                case .ready: finish(true)
                case .waiting(let error), .failed(let error):
                    progress.error = "\(error)"
                    if progress.announceOnce() {
                        DispatchQueue.main.async { note("학교 서버에 연결하는 중입니다. macOS가 '로컬 네트워크' 허용을 물으면 허용을 눌러 주세요.\n") }
                    }
                    finish(false)
                default: break
                }
            }
            conn.start(queue: .global())
            DispatchQueue.global().asyncAfter(deadline: .now() + 4) { finish(false) }
        }
        attempt()
    }
}
