import CoreLocation
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

    private enum RouteType: String, CaseIterable {
        case walking = "步行道路"
        case direct = "直線"
    }

    @Environment(\.scenePhase) private var scenePhase
    @State private var simulation = LocationSimulation()
    @State private var hasPairing = LocationSimulation.hasSavedPairing
    @State private var importingPairing = false
    @State private var mode = Mode.location
    @State private var coordinateText = ""
    @State private var startText = ""
    @State private var endText = ""
    @State private var routeType = RouteType.walking
    @State private var speedKPH: Double = 5
    @State private var backgroundPlayback = true
    @State private var isInBackground = false
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
                case .location: locationSection
                case .movement: movementSection
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
            .onChange(of: scenePhase, initial: true) { _, phase in
                isInBackground = phase == .background
            }
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
            coordinateField("緯度, 經度", text: $coordinateText)
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
            coordinateField("起點緯度, 經度", text: $startText)
            coordinateField("終點緯度, 經度", text: $endText)
            Picker("路線", selection: $routeType) {
                ForEach(RouteType.allCases, id: \.self) { option in
                    Text(option.rawValue).tag(option)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("速度")
                    Spacer()
                    Text("\(Int(speedKPH)) km/h").monospacedDigit()
                }
                Slider(value: $speedKPH, in: 1...100, step: 1)
                    .accessibilityLabel("移動速度")
                    .accessibilityValue("\(Int(speedKPH)) 公里每小時")
            }
            Toggle("切換 App 時繼續移動", isOn: $backgroundPlayback)
            Button("開始移動", systemImage: "point.bottomleft.forward.to.point.topright.scurvepath") {
                guard let startCoordinates, let endCoordinates else { return }
                startMovement(from: startCoordinates, to: endCoordinates)
            }
            .disabled(!hasPairing || startCoordinates == nil || endCoordinates == nil || startCoordinates == endCoordinates)
        } footer: {
            if (!startText.isEmpty && startCoordinates == nil) || (!endText.isEmpty && endCoordinates == nil) {
                Text("請輸入有效的緯度和經度，例如 25.0339, 121.5644。")
            } else if let startCoordinates, startCoordinates == endCoordinates {
                Text("起點和終點必須是不同的位置。")
            } else if backgroundPlayback {
                Text("開始前請連接 LocalDevVPN。允許定位權限後，切換 App 時可以繼續移動。")
            } else {
                Text("開始前請連接 LocalDevVPN。切換 App 時會暫停移動。")
            }
        }
        .disabled(busy)
    }

    private func coordinateField(_ title: String, text: Binding<String>) -> some View {
        TextField(title, text: text)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .keyboardType(.numbersAndPunctuation)
            .accessibilityLabel(title)
    }

    private func startMovement(from start: Coordinates, to end: Coordinates) {
        guard !busy else { return }
        let routeType = routeType
        let speedKPH = speedKPH
        let backgroundPlayback = backgroundPlayback
        movementTask = Task {
            defer {
                movementTask = nil
                movementProgress = nil
                observedSimulatedLocation = false
            }
            do {
                let route = switch routeType {
                case .walking: try await MovementRoute.walking(from: start, to: end)
                case .direct: try MovementRoute(points: [start, end])
                }
                try Task.checkCancellation()
                try await playMovement(route, speedKPH: speedKPH, backgroundPlayback: backgroundPlayback)
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

    private func playMovement(_ route: MovementRoute, speedKPH: Double, backgroundPlayback: Bool) async throws {
        let backgroundSession = backgroundPlayback && !isInBackground ? CLBackgroundActivitySession() : nil
        let manager = backgroundSession == nil ? nil : CLLocationManager()
        let monitoring: Task<Void, Never>? = if backgroundSession != nil {
            Task {
                do {
                    for try await update in CLLocationUpdate.liveUpdates(.otherNavigation) {
                        try Task.checkCancellation()
                        if let location = update.location {
                            observedSimulatedLocation = location.sourceInformation?.isSimulatedBySoftware == true
                        }
                    }
                } catch where !Task.isCancelled {
                    observedSimulatedLocation = false
                } catch {
                    // A new route may already be starting after this monitor is cancelled.
                }
            }
        } else {
            nil
        }
        defer {
            monitoring?.cancel()
            backgroundSession?.invalidate()
        }

        try await route.play(speedKPH: speedKPH) {
            !isInBackground || manager?.authorizationStatus == .authorizedWhenInUse ||
                manager?.authorizationStatus == .authorizedAlways
        } update: { coordinates, progress in
            try await simulation.setLocation(coordinates)
            try Task.checkCancellation()
            movementProgress = progress
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
