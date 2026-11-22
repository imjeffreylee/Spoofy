import CoreLocation
import Foundation

@MainActor
final class MovementLocationSession: NSObject, @preconcurrency CLLocationManagerDelegate {
    // Core Location uses the run loop of the thread that creates the manager.
    private let manager = CLLocationManager()
    private let authorizationEvents = AsyncStream<CLAuthorizationStatus>.makeStream(bufferingPolicy: .bufferingNewest(1))
    private let reportSimulatedLocation: (Bool) -> Void
    private var isMonitoring = false

    init(reportSimulatedLocation: @escaping (Bool) -> Void) {
        self.reportSimulatedLocation = reportSimulatedLocation
        super.init()
        manager.delegate = self
        manager.activityType = .otherNavigation
        manager.allowsBackgroundLocationUpdates = true
        manager.pausesLocationUpdatesAutomatically = false
        manager.showsBackgroundLocationIndicator = true
    }

    func start() async throws {
        try Task.checkCancellation()
        if manager.authorizationStatus == .notDetermined {
            manager.requestWhenInUseAuthorization()
            for await status in authorizationEvents.stream where status != .notDetermined {
                break
            }
        }
        try Task.checkCancellation()
        try requireAuthorization()
        isMonitoring = true
        manager.startUpdatingLocation()
    }

    func requireAuthorization() throws {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: break
        default: throw LocationPermissionRequired()
        }
    }

    func stop() {
        isMonitoring = false
        manager.stopUpdatingLocation()
        authorizationEvents.continuation.finish()
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationEvents.continuation.yield(manager.authorizationStatus)
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard isMonitoring, let location = locations.last else { return }
        reportSimulatedLocation(location.sourceInformation?.isSimulatedBySoftware == true)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: any Error) {
        if isMonitoring { reportSimulatedLocation(false) }
    }

    private struct LocationPermissionRequired: LocalizedError {
        var errorDescription: String? {
            "模擬移動需要定位權限。請到 iPhone 的「設定 → App → Spoofy → 位置」選擇「使用 App 期間」。"
        }
    }
}
