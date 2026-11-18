import Foundation
import SwiftUI

// Headless mode for testing over ssh: LOCAL_AGENT_AUTORUN=1 LOCAL_AGENT_TOKEN=... runs the install and exits.
if ProcessInfo.processInfo.environment["LOCAL_AGENT_AUTORUN"] != nil {
    guard let p = Installer.makeProcess(token: ProcessInfo.processInfo.environment["LOCAL_AGENT_TOKEN"] ?? "") else {
        print("bundle is missing its install files"); exit(1)
    }
    p.standardOutput = FileHandle.standardOutput
    p.standardError = FileHandle.standardOutput
    try p.run()
    p.waitUntilExit()
    exit(p.terminationStatus)
}

final class Model: ObservableObject {
    @Published var log = ""
    @Published var running = false
    @Published var succeeded: Bool?

    func install(token: String) {
        guard let p = Installer.makeProcess(token: token.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            log = "앱 안에 설치 파일이 없습니다. 앱을 다시 받아 주세요.\n"; succeeded = false; return
        }
        log = ""; succeeded = nil; running = true
        log = "학교 서버(\(Gateway.host))에 연결할 수 있는지 확인합니다…\n"
        Gateway.waitUntilReachable(note: { [weak self] in self?.log += $0 }, done: { [weak self] error in
            guard let self = self else { return }
            if let error = error {
                self.log += "연결하지 못했습니다(\(error)). 학교 네트워크에 연결돼 있는지, 시스템 설정 → 개인정보 보호 및 보안 → 로컬 네트워크에서 이 앱이 켜져 있는지 확인해 주세요.\n"
                self.running = false; self.succeeded = false
                self.reportForTest(status: 1)
                return
            }
            self.log += "연결됐습니다.\n"
            self.launch(p)
        })
    }

    private func reportForTest(status: Int32) {
        // Test hook: LOCAL_AGENT_AUTOCLICK=<file> presses the button on launch and writes the result there.
        if let file = ProcessInfo.processInfo.environment["LOCAL_AGENT_AUTOCLICK"] {
            try? "exit=\(status)\n\(log)".write(toFile: file, atomically: true, encoding: .utf8)
            exit(0)
        }
    }

    private func launch(_ p: Process) {
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async { self?.log += text }
        }
        p.terminationHandler = { [weak self] proc in
            pipe.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async {
                self?.running = false; self?.succeeded = proc.terminationStatus == 0
                self?.reportForTest(status: proc.terminationStatus)
            }
        }
        do { try p.run() } catch {
            log = "설치를 시작하지 못했습니다: \(error.localizedDescription)\n"; running = false; succeeded = false
        }
    }
}

struct ContentView: View {
    @StateObject private var model = Model()
    @State private var token = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Local Agent 설치").font(.title2.bold())
            Text("학교 Mac mini의 로컬 모델을 Claude Code·Codex에서 쓸 수 있게 설치합니다. 학교 네트워크에 연결돼 있어야 하고, 몇 분 걸립니다.")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            SecureField("토큰 (이미 설치했다면 비워 두세요)", text: $token)
                .textFieldStyle(.roundedBorder).disabled(model.running)
            HStack(spacing: 10) {
                Button(model.running ? "설치 중…" : "설치") { model.install(token: token) }
                    .keyboardShortcut(.defaultAction).disabled(model.running)
                if model.running { ProgressView().controlSize(.small) }
                if model.succeeded == true {
                    Label("끝났습니다. Claude Code를 새로 열면 쓸 수 있습니다.", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                } else if model.succeeded == false {
                    Label("문제가 생겼습니다. 아래 내용을 개발자에게 보내 주세요.", systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red)
                }
            }
            ScrollViewReader { proxy in
                ScrollView {
                    Text(model.log.isEmpty ? "설치 기록이 여기에 나옵니다." : model.log)
                        .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Color.clear.frame(height: 1).id("end")
                }
                .padding(8).background(.quaternary.opacity(0.5)).clipShape(RoundedRectangle(cornerRadius: 6))
                .onChange(of: model.log) { _ in proxy.scrollTo("end") }
            }
        }
        .padding(20).frame(width: 540, height: 440)
        .onAppear {
            if let _ = ProcessInfo.processInfo.environment["LOCAL_AGENT_AUTOCLICK"] {
                model.install(token: ProcessInfo.processInfo.environment["LOCAL_AGENT_TOKEN"] ?? "")
            }
        }
    }
}

struct InstallerApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }.windowResizability(.contentSize)
    }
}

InstallerApp.main()
