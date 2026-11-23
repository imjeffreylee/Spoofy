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
    private enum Mode: String, CaseIterable {
        case location = "設定座標"
        case movement = "模擬移動"
    }

    @AppStorage("lastMovement") private var lastMovementData: Data?
    @State private var simulation = LocationSimulation()
    @State private var hasPairing = LocationSimulation.hasSavedPairing
    @State private var importingPairing = false
    @State private var mode = Mode.location
    @State private var coordinateText = ""
    @State private var startText = ""
    @State private var endText = ""
    @State private var routeType = MovementSettings.RouteType.walking
    @State private var speedKPH: Double = 19
    @State private var movementTask: Task<Void, Never>?
    @State private var movementProgress: Double?
    @State private var observedSimulatedLocation = false
    @State private var operation: String?
    @State private var message: String?
    @State private var failed = false

    private var coordinates: Coordinates? { Coordinates(text: coordinateText) }
    private var startCoordinates: Coordinates? { Coordinates(text: startText) }
    private var endCoordinates: Coordinates? { Coordinates(text: endText) }
    private var busy: Bool { operation != nil || movementTask != nil }

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
                    Picker("模擬方式", selection: $mode) {
                        ForEach(Mode.allCases, id: \.self) { option in
                            Text(option.rawValue).tag(option)
                        }
                    }
                    .pickerStyle(.segmented)
                    .disabled(busy)
                }

                switch mode {
                case .location:
                    locationSection
                case .movement:
                    if let lastMovement = MovementSettings.restore(from: lastMovementData) {
                        Section {
                            Button("開始上次路線", systemImage: "arrow.counterclockwise") {
                                startText = "\(lastMovement.start.latitude), \(lastMovement.start.longitude)"
                                endText = "\(lastMovement.end.latitude), \(lastMovement.end.longitude)"
                                routeType = lastMovement.routeType
                                speedKPH = lastMovement.speedKPH
                                startMovement(lastMovement)
                            }
                            .disabled(!hasPairing || busy)
                        }
                    }
                    movementSection
                }

                Section {
                    Button("停止模擬", systemImage: "stop.circle") {
                        perform("正在清除模擬定位", cancelling: movementTask) {
                            try await simulation.clearLocation()
                            return "已送出清除指令。請到 Apple 地圖確認實際位置。"
                        }
                    }
                    .disabled(!hasPairing || operation != nil)
                }

                if let operation {
                    Section {
                        ProgressView(operation)
                    }
                } else if let movementProgress {
                    Section {
                        ProgressView(value: movementProgress) {
                            Text("移動中 · \(movementProgress.formatted(.percent.precision(.fractionLength(0))))")
                        }
                        if observedSimulatedLocation {
                            Label("iPhone 正在回報模擬位置", systemImage: "location.fill")
                                .foregroundStyle(.secondary)
                        }
                    }
                } else if movementTask != nil {
                    Section {
                        ProgressView("正在準備路線")
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

    private var locationSection: some View {
        Section {
            CoordinateField(title: "緯度, 經度", text: $coordinateText)
            Button("設定座標", systemImage: "location.fill") {
                guard let coordinates else { return }
                perform("正在設定座標") {
                    try await simulation.setLocation(coordinates)
                    return "已送出座標 \(coordinates.latitude), \(coordinates.longitude)。請到 Apple 地圖確認。"
                }
            }
            .disabled(!hasPairing || coordinates == nil || busy)
        } footer: {
            if !coordinateText.isEmpty && coordinates == nil {
                Text("請輸入有效的緯度和經度，例如 25.0339, 121.5644。")
            } else {
                Text("開始前請連接 LocalDevVPN。")
            }
        }
    }

    private var movementSection: some View {
        Section {
            CoordinateField(title: "起點緯度, 經度", text: $startText)
            CoordinateField(title: "終點緯度, 經度", text: $endText)
            Picker("路線", selection: $routeType) {
                ForEach(MovementSettings.RouteType.allCases, id: \.self) { option in
                    Text(option.title).tag(option)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("速度")
                    Spacer()
                    Text("\(Int(speedKPH)) km/h").monospacedDigit()
                }
                Slider(value: $speedKPH, in: MovementRoute.speedRange, step: 1)
                    .accessibilityLabel("移動速度")
                    .accessibilityValue("\(Int(speedKPH)) 公里每小時")
            }
            Button("開始移動", systemImage: "point.bottomleft.forward.to.point.topright.scurvepath") {
                guard let startCoordinates, let endCoordinates else { return }
                startMovement(MovementSettings(start: startCoordinates, end: endCoordinates, routeType: routeType, speedKPH: speedKPH))
            }
            .disabled(!hasPairing || startCoordinates == nil || endCoordinates == nil || startCoordinates == endCoordinates)
        } footer: {
            if (!startText.isEmpty && startCoordinates == nil) || (!endText.isEmpty && endCoordinates == nil) {
                Text("請輸入有效的緯度和經度，例如 25.0339, 121.5644。")
            } else if let startCoordinates, startCoordinates == endCoordinates {
                Text("起點和終點必須是不同的位置。")
            } else {
                Text("請先連接 LocalDevVPN 並允許定位權限，讓路線能在切換 App 後繼續播放。")
            }
        }
        .disabled(busy)
    }

    private func startMovement(_ settings: MovementSettings) {
        guard hasPairing, !busy, settings.isValid else { return }
        movementTask = Task {
            let locationSession = MovementLocationSession {
                observedSimulatedLocation = $0
            }
            defer {
                locationSession.stop()
                movementTask = nil
                movementProgress = nil
                observedSimulatedLocation = false
            }
            do {
                try await locationSession.start()
                let route = switch settings.routeType {
                case .walking: try await MovementRoute.walking(from: settings.start, to: settings.end)
                case .direct: try MovementRoute(points: [settings.start, settings.end])
                }
                try Task.checkCancellation()
                try await route.play(speedKPH: settings.speedKPH) { coordinates, progress in
                    try locationSession.requireAuthorization()
                    try await simulation.setLocation(coordinates)
                    if progress == 0, let data = try? JSONEncoder().encode(settings) {
                        lastMovementData = data
                    }
                    try Task.checkCancellation()
                    movementProgress = progress
                }
                try Task.checkCancellation()
                message = "已抵達終點。點「停止模擬」可恢復實際定位。"
                failed = false
            } catch where !Task.isCancelled {
                message = error.localizedDescription
                failed = true
            } catch {
                // The Stop action clears the location after this task exits.
            }
        }
    }

    private func perform(
        _ progress: String,
        cancelling movement: Task<Void, Never>? = nil,
        action: @escaping @MainActor () async throws -> String
    ) {
        guard operation == nil, movementTask == nil || movement != nil else { return }
        operation = progress
        movement?.cancel()
        Task {
            defer { operation = nil }
            await movement?.value
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

private struct CoordinateField: View {
    let title: String
    @Binding var text: String
    @FocusState private var isFocused: Bool

    var body: some View {
        HStack {
            TextField(title, text: $text)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.numbersAndPunctuation)
                .focused($isFocused)
                .accessibilityLabel(title)

            if !text.isEmpty {
                Button {
                    text = ""
                    isFocused = true
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("清除\(title)")
            }
        }
        .frame(minHeight: 44)
    }
}
