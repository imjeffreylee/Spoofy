import SwiftUI
import UniformTypeIdentifiers

@main
struct SpoofyApp: App {
    var body: some Scene {
        WindowGroup {
            SimulationView()
        }
    }
}

private struct SimulationView: View {
    @State private var simulation = LocationSimulation()
    @State private var hasPairing = LocationSimulation.hasSavedPairing
    @State private var importingPairing = false
    @State private var coordinateText = ""
    @State private var operation: String?
    @State private var message: String?
    @State private var failed = false

    private var coordinates: Coordinates? { Coordinates(text: coordinateText) }
    private var busy: Bool { operation != nil }

    var body: some View {
        NavigationStack {
            Form {
                Section("裝置配對") {
                    Label(
                        hasPairing ? "已匯入配對紀錄" : "尚未匯入配對紀錄",
                        systemImage: hasPairing ? "checkmark.circle" : "iphone"
                    )
                    Button(hasPairing ? "更換配對紀錄" : "匯入配對紀錄") {
                        importingPairing = true
                    }
                    .disabled(busy)
                }

                Section {
                    TextField("緯度, 經度", text: $coordinateText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.numbersAndPunctuation)
                        .accessibilityLabel("緯度和經度")
                    Button("設定座標", systemImage: "location.fill") {
                        guard let coordinates else { return }
                        perform("正在設定座標") {
                            try await simulation.setLocation(coordinates)
                            return "已送出座標 \(coordinates.latitude), \(coordinates.longitude)。請到 Apple 地圖確認。"
                        }
                    }
                    .disabled(!hasPairing || coordinates == nil || busy)
                    Button("停止模擬", systemImage: "stop.circle") {
                        perform("正在清除模擬定位") {
                            try await simulation.clearLocation()
                            return "已送出清除指令。請到 Apple 地圖確認實際位置。"
                        }
                    }
                    .disabled(!hasPairing || busy)
                } header: {
                    Text("定位模擬")
                } footer: {
                    if !coordinateText.isEmpty && coordinates == nil {
                        Text("請輸入有效的緯度和經度，例如 25.0339, 121.5644。")
                    } else {
                        Text("開始前請連接 LocalDevVPN。")
                    }
                }

                if let operation {
                    Section {
                        ProgressView(operation)
                    }
                } else if let message {
                    Section {
                        Label(message, systemImage: failed ? "exclamationmark.circle" : "info.circle")
                            .foregroundStyle(failed ? Color.red : Color.primary)
                    }
                }
            }
            .navigationTitle("Spoofy")
            .fileImporter(isPresented: $importingPairing, allowedContentTypes: [.data]) { result in
                switch result {
                case let .success(url):
                    perform("正在匯入配對紀錄") {
                        try await simulation.importPairing(from: url)
                        hasPairing = true
                        return "配對紀錄已儲存在這支 iPhone。"
                    }
                case let .failure(error):
                    message = error.localizedDescription
                    failed = true
                }
            }
        }
    }

    private func perform(_ progress: String, action: @escaping @MainActor () async throws -> String) {
        guard !busy else { return }
        operation = progress
        Task {
            defer { operation = nil }
            do {
                message = try await action()
                failed = false
            } catch {
                message = error.localizedDescription
                failed = true
            }
        }
    }
}
