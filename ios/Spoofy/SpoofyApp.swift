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
        case savedPlaces = "已存的地點"
    }

    private struct SavedPlace: Codable, Identifiable {
        let id: UUID
        var name: String
        let coordinates: Coordinates
    }

    private enum PlaceDialog {
        case add(Coordinates)
        case rename(UUID)
        case delete(UUID)

        var title: String {
            switch self {
            case .add: "地點名稱"
            case .rename: "編輯地點名稱"
            case .delete: "刪除地點"
            }
        }
    }

    private static let savedPlaceLimit = 20

    @AppStorage("lastMovement") private var lastMovementData: Data?
    @AppStorage("savedPlaces") private var savedPlacesData: Data?
    @State private var simulation = LocationSimulation()
    @State private var hasPairing = LocationSimulation.hasSavedPairing
    @State private var importingPairing = false
    @State private var mode = Mode.location
    @State private var coordinateText = ""
    @State private var placeDialog: PlaceDialog?
    @State private var placeName = ""
    @State private var startText = ""
    @State private var endText = ""
    @State private var routeType = MovementSettings.RouteType.walking
    @State private var speedKPH: Double = 19
    @State private var movementTask: Task<Void, Never>?
    @State private var locationHoldTask: Task<Void, Never>?
    @State private var movementProgress: Double?
    @State private var observedSimulatedLocation = false
    @State private var operation: String?
    @State private var message: String?
    @State private var failed = false

    private var coordinates: Coordinates? { Coordinates(text: coordinateText) }
    private var startCoordinates: Coordinates? { Coordinates(text: startText) }
    private var endCoordinates: Coordinates? { Coordinates(text: endText) }
    private var busy: Bool { operation != nil || movementTask != nil }
    private var trimmedPlaceName: String { placeName.trimmingCharacters(in: .whitespacesAndNewlines) }

    private var savedPlaces: [SavedPlace] {
        guard let savedPlacesData else { return [] }
        return (try? JSONDecoder().decode([SavedPlace].self, from: savedPlacesData)) ?? []
    }

    private var isPlaceDialogPresented: Binding<Bool> {
        Binding(
            get: { placeDialog != nil },
            set: { isPresented in
                if !isPresented { placeDialog = nil }
            }
        )
    }

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
                case .savedPlaces:
                    savedPlacesSection
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
            .alert(placeDialog?.title ?? "", isPresented: isPlaceDialogPresented, presenting: placeDialog) { dialog in
                switch dialog {
                case let .add(coordinates):
                    placeNameActions { addPlace(at: coordinates) }
                case let .rename(id):
                    placeNameActions { renamePlace(id) }
                case let .delete(id):
                    Button("取消", role: .cancel) {}
                    Button("刪除", role: .destructive) { deletePlace(id) }
                }
            } message: { dialog in
                if case .delete = dialog {
                    Text("確定要刪除地點嗎？")
                }
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
        let reachedLimit = savedPlaces.count >= Self.savedPlaceLimit
        return Section {
            CoordinateField(title: "緯度, 經度", text: $coordinateText)
            Button("設定座標", systemImage: "location.fill") {
                guard let coordinates else { return }
                setLocation(coordinates)
            }
            .disabled(!hasPairing || coordinates == nil || busy)
            HStack {
                Button("儲存地點", systemImage: "bookmark") {
                    guard let coordinates else { return }
                    placeName = ""
                    placeDialog = .add(coordinates)
                }
                .disabled(coordinates == nil || busy || reachedLimit)
                if reachedLimit {
                    Spacer()
                    Text("已達到上限\(Self.savedPlaceLimit)筆")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
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

    private var savedPlacesSection: some View {
        let places = savedPlaces
        return Section {
            if places.isEmpty {
                Text("尚未儲存地點")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(places) { place in
                    Button(place.name) {
                        setLocation(place.coordinates)
                    }
                    .disabled(!hasPairing)
                    .swipeActions(allowsFullSwipe: false) {
                        Button {
                            placeDialog = .delete(place.id)
                        } label: {
                            Label("刪除", systemImage: "trash")
                        }
                        .tint(.red)

                        Button {
                            placeName = place.name
                            placeDialog = .rename(place.id)
                        } label: {
                            Label("編輯", systemImage: "pencil")
                        }
                        .tint(.blue)
                    }
                }
            }
        }
        .disabled(busy)
    }

    @ViewBuilder
    private func placeNameActions(onSave: @escaping () -> Void) -> some View {
        TextField("輸入地點名稱", text: $placeName)
        Button("取消", role: .cancel) {}
        Button("儲存", action: onSave)
            .disabled(trimmedPlaceName.isEmpty)
    }

    private func addPlace(at coordinates: Coordinates) {
        let places = savedPlaces
        let name = trimmedPlaceName
        guard places.count < Self.savedPlaceLimit, !name.isEmpty else { return }

        let place = SavedPlace(id: UUID(), name: name, coordinates: coordinates)
        updateSavedPlaces(places + [place], successMessage: "已儲存地點「\(name)」。")
    }

    private func renamePlace(_ id: UUID) {
        var places = savedPlaces
        let name = trimmedPlaceName
        guard !name.isEmpty, let index = places.firstIndex(where: { $0.id == id }) else { return }

        places[index].name = name
        updateSavedPlaces(places, successMessage: "已更新地點名稱為「\(name)」。")
    }

    private func deletePlace(_ id: UUID) {
        var places = savedPlaces
        guard let index = places.firstIndex(where: { $0.id == id }) else { return }

        let place = places.remove(at: index)
        updateSavedPlaces(places, successMessage: "已刪除地點「\(place.name)」。")
    }

    private func updateSavedPlaces(_ places: [SavedPlace], successMessage: String) {
        do {
            savedPlacesData = try JSONEncoder().encode(places)
            message = successMessage
            failed = false
        } catch {
            message = "無法更新已存的地點。"
            failed = true
        }
    }

    private func setLocation(_ coordinates: Coordinates) {
        guard hasPairing, coordinates.isValid else { return }
        perform("正在設定座標") {
            let locationSession = SimulationLocationSession { _ in }
            defer {
                if locationHoldTask == nil { locationSession.stop() }
            }
            do {
                try await locationSession.start()
            } catch is SimulationLocationSession.LocationPermissionRequired {
                // A one-time location command is still available without Core Location permission.
            }
            try await simulation.setLocation(coordinates)
            guard locationSession.isMonitoring else {
                return "已送出座標。允許 Spoofy 在使用期間取用位置，即可在切換 App 後維持定位。"
            }
            let status = "正在維持座標 \(coordinates.latitude), \(coordinates.longitude)。"
            holdLocation(coordinates, using: locationSession, status: status)
            return status
        }
    }

    private func startMovement(_ settings: MovementSettings) {
        guard hasPairing, !busy, settings.isValid else { return }
        let previousHold = locationHoldTask
        previousHold?.cancel()
        movementTask = Task {
            await previousHold?.value
            let locationSession = SimulationLocationSession {
                observedSimulatedLocation = $0
            }
            defer {
                if locationHoldTask == nil { locationSession.stop() }
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
                let status = "已抵達終點，正在維持終點座標。"
                holdLocation(settings.end, using: locationSession, status: status)
                message = status
                failed = false
            } catch where !Task.isCancelled {
                message = error.localizedDescription
                failed = true
            } catch {
                // The Stop action clears the location after this task exits.
            }
        }
    }

    private func holdLocation(_ coordinates: Coordinates, using session: SimulationLocationSession, status: String) {
        locationHoldTask = Task {
            defer {
                session.stop()
                locationHoldTask = nil
                observedSimulatedLocation = false
            }
            var failures = 0
            do {
                while true {
                    try await Task.sleep(for: .seconds(10))
                    try session.requireAuthorization()
                    do {
                        // The send also reopens a stale connection if it has dropped in the background.
                        try await simulation.setLocation(coordinates)
                        try Task.checkCancellation()
                        if failures > 0 {
                            failures = 0
                            message = status
                            failed = false
                        }
                    } catch {
                        try Task.checkCancellation()
                        failures += 1
                        if failures >= 3 { throw error }
                        message = "模擬定位連線中斷，正在重新連線。"
                        failed = false
                    }
                }
            } catch where !Task.isCancelled {
                message = error.localizedDescription
                failed = true
            } catch {
                // Stop and replacement actions wait for this task before writing another location.
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
        let previousHold = locationHoldTask
        previousHold?.cancel()
        movement?.cancel()
        Task {
            defer { operation = nil }
            await movement?.value
            await previousHold?.value
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
