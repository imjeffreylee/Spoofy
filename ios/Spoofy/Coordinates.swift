import Foundation

struct Coordinates: Codable, Equatable, Sendable {
    let latitude: Double
    let longitude: Double

    init(latitude: Double, longitude: Double) {
        self.latitude = latitude
        self.longitude = longitude
    }

    var isValid: Bool {
        (-90.0...90.0).contains(latitude) && (-180.0...180.0).contains(longitude)
    }

    init?(text: String) {
        var coordinateText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if (coordinateText.hasPrefix("(") && coordinateText.hasSuffix(")")) ||
            (coordinateText.hasPrefix("（") && coordinateText.hasSuffix("）")) {
            coordinateText.removeFirst()
            coordinateText.removeLast()
        }

        let values = coordinateText.replacingOccurrences(of: "，", with: ",")
            .split(separator: ",", omittingEmptySubsequences: false)
        guard values.count == 2,
              let latitude = Double(values[0].trimmingCharacters(in: .whitespacesAndNewlines)),
              let longitude = Double(values[1].trimmingCharacters(in: .whitespacesAndNewlines)) else {
            return nil
        }
        self.init(latitude: latitude, longitude: longitude)
        guard isValid else { return nil }
    }
}
