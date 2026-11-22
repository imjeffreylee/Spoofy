import CoreLocation
import Foundation
import MapKit

struct MovementRoute {
    static let speedRange = 1.0...20.0

    private struct Waypoint {
        let coordinates: Coordinates
        let distance: Double
    }

    private let waypoints: [Waypoint]
    let distance: Double

    init(points: [Coordinates]) throws {
        guard let start = points.first else { throw Failure.emptyRoute }
        var waypoints = [Waypoint(coordinates: start, distance: 0)]
        var previous = start.location
        var distance: Double = 0
        for coordinates in points.dropFirst() {
            let location = coordinates.location
            let segmentLength = previous.distance(from: location)
            guard segmentLength.isFinite else { throw Failure.emptyRoute }
            if segmentLength > 0 {
                distance += segmentLength
                waypoints.append(Waypoint(coordinates: coordinates, distance: distance))
                previous = location
            }
        }
        guard distance > 0.01 else { throw Failure.emptyRoute }
        self.waypoints = waypoints
        self.distance = distance
    }

    @MainActor
    static func walking(from start: Coordinates, to end: Coordinates) async throws -> Self {
        let request = MKDirections.Request()
        request.source = start.mapItem
        request.destination = end.mapItem
        request.transportType = .walking
        let directions = WalkingDirections(request: request)
        let response: MKDirections.Response
        do {
            response = try await withTaskCancellationHandler {
                try await directions.calculate()
            } onCancel: {
                Task { await directions.cancel() }
            }
        } catch {
            try Task.checkCancellation()
            throw Failure.noWalkingRoute
        }
        try Task.checkCancellation()
        guard let polyline = response.routes.first?.polyline, polyline.pointCount > 1 else {
            throw Failure.noWalkingRoute
        }
        var coordinates = Array(repeating: CLLocationCoordinate2D(), count: polyline.pointCount)
        polyline.getCoordinates(&coordinates, range: NSRange(location: 0, length: coordinates.count))
        let route = coordinates.map { Coordinates(latitude: $0.latitude, longitude: $0.longitude) }
        return try Self(points: [start] + route + [end])
    }

    func position(at distance: Double) -> Coordinates {
        if distance <= 0 { return waypoints[0].coordinates }
        if distance >= self.distance { return waypoints[waypoints.count - 1].coordinates }

        var lower = 1
        var upper = waypoints.count - 1
        while lower < upper {
            let middle = (lower + upper) / 2
            if waypoints[middle].distance < distance {
                lower = middle + 1
            } else {
                upper = middle
            }
        }

        let start = waypoints[lower - 1]
        let end = waypoints[lower]
        if distance == end.distance { return end.coordinates }
        let fraction = (distance - start.distance) / (end.distance - start.distance)
        let latitude = start.coordinates.latitude + fraction * (end.coordinates.latitude - start.coordinates.latitude)
        let longitudeDelta = (end.coordinates.longitude - start.coordinates.longitude + 540)
            .truncatingRemainder(dividingBy: 360) - 180
        let longitude = (start.coordinates.longitude + fraction * longitudeDelta + 540)
            .truncatingRemainder(dividingBy: 360) - 180
        return Coordinates(latitude: latitude, longitude: longitude)
    }

    @MainActor
    func play(
        speedKPH: Double,
        update: (Coordinates, Double) async throws -> Void
    ) async throws {
        guard Self.speedRange.contains(speedKPH) else { throw Failure.invalidSpeed }
        try Task.checkCancellation()
        try await update(position(at: 0), 0)

        let clock = ContinuousClock()
        let metersPerSecond = speedKPH / 3.6
        var lastTick = clock.now
        var traveled: Double = 0
        while traveled < distance {
            let interval = min(1, (distance - traveled) / metersPerSecond)
            try await clock.sleep(until: lastTick.advanced(by: .seconds(interval)))
            let now = clock.now
            let elapsed = lastTick.duration(to: now).components
            lastTick = now
            let seconds = Double(elapsed.seconds) + Double(elapsed.attoseconds) / 1e18
            // Limit progress on resumption after iOS suspends the app.
            traveled = min(distance, traveled + min(seconds, 1.5) * metersPerSecond)
            try Task.checkCancellation()
            try await update(position(at: traveled), traveled / distance)
        }
    }

    private enum Failure: LocalizedError {
        case emptyRoute, noWalkingRoute, invalidSpeed

        var errorDescription: String? {
            switch self {
            case .emptyRoute: "起點和終點必須是不同的位置。"
            case .noWalkingRoute: "Apple 地圖找不到步行路線。請確認網路連線，或改用直線。"
            case .invalidSpeed: "移動速度須介於 1 到 20 公里／小時。"
            }
        }
    }
}

@MainActor
private final class WalkingDirections {
    private let directions: MKDirections

    init(request: MKDirections.Request) {
        directions = MKDirections(request: request)
    }

    func calculate() async throws -> MKDirections.Response {
        try await directions.calculate()
    }

    func cancel() {
        directions.cancel()
    }
}

private extension Coordinates {
    var location: CLLocation { CLLocation(latitude: latitude, longitude: longitude) }

    @MainActor
    var mapItem: MKMapItem {
        if #available(iOS 26.0, macOS 26.0, *) {
            return MKMapItem(location: location, address: nil)
        } else {
            return MKMapItem(placemark: MKPlacemark(coordinate: location.coordinate))
        }
    }
}
