import Darwin
import Dispatch
import Foundation
import IDevice

actor LocationSimulation {
    private let queue = DispatchSerialQueue(label: "app.spoofy.location-simulation")
    nonisolated var unownedExecutor: UnownedSerialExecutor { queue.asUnownedSerialExecutor() }

    private static let pairingDirectory = URL.applicationSupportDirectory.appending(path: "Spoofy")
    private static let pairingFile = pairingDirectory.appending(path: "pairing.plist")
    private var connection: Connection?

    static var hasSavedPairing: Bool {
        FileManager.default.fileExists(atPath: pairingFile.path)
    }

    func importPairing(from url: URL) throws {
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }

        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let maximumSize = 1_048_576
        guard let data = try file.read(upToCount: maximumSize + 1),
              !data.isEmpty, data.count <= maximumSize else {
            throw Failure.pairingFileSize
        }
        var pairing: OpaquePointer?
        defer { rp_pairing_file_free(pairing) }
        try data.withUnsafeBytes { bytes in
            try Self.check(
                rp_pairing_file_from_bytes(bytes.bindMemory(to: UInt8.self).baseAddress, UInt(bytes.count), &pairing),
                message: "無法讀取配對紀錄。請選擇這支 iPhone 的 RPPairing 檔案。"
            )
        }

        var directory = Self.pairingDirectory
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var properties = URLResourceValues()
        properties.isExcludedFromBackup = true
        try directory.setResourceValues(properties)
        try data.write(to: Self.pairingFile, options: [.atomic, .completeFileProtection])
        connection = nil
    }

    func setLocation(_ coordinates: Coordinates) throws {
        let session = try connectIfNeeded()
        do {
            try Self.check(
                location_simulation_set(session.location, coordinates.latitude, coordinates.longitude),
                message: "無法設定模擬座標。請確認 LocalDevVPN 後重試。"
            )
        } catch {
            connection = nil
            throw error
        }
    }

    func clearLocation() throws {
        let session = try connectIfNeeded()
        defer { connection = nil }
        try Self.check(
            location_simulation_clear(session.location),
            message: "無法送出清除指令。請確認 LocalDevVPN 後重試。"
        )
    }

    private func connectIfNeeded() throws -> Connection {
#if targetEnvironment(simulator)
        throw Failure.requiresIPhone
#else
        if let connection { return connection }
        guard Self.hasSavedPairing else { throw Failure.missingPairing }

        idevice_set_global_timeout(10)
        var pairing: OpaquePointer?
        defer { rp_pairing_file_free(pairing) }
        try Self.pairingFile.path.withCString { path in
            try Self.check(
                rp_pairing_file_read(path, &pairing),
                message: "無法讀取已儲存的配對紀錄。請重新匯入。"
            )
        }

        let addressLength = MemoryLayout<sockaddr_in>.size
        var address = sockaddr_in()
        address.sin_len = UInt8(addressLength)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = UInt16(49_152).bigEndian
        // LocalDevVPN's default device address.
        address.sin_addr.s_addr = inet_addr("10.7.0.1")

        let session = Connection()
        try withUnsafePointer(to: &address) { addressPointer in
            try addressPointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                try Self.check(
                    tunnel_create_rppairing(
                        socketAddress, socklen_t(addressLength), "Spoofy", pairing, nil, nil,
                        &session.adapter, &session.handshake
                    ),
                    message: "無法連到這支 iPhone。請確認開發者模式、LocalDevVPN 和配對紀錄。"
                )
            }
        }
        try Self.check(
            remote_server_connect_rsd(session.adapter, session.handshake, &session.server),
            message: "無法開啟開發者服務。請確認 iOS 的開發者支援已就緒。"
        )
        try Self.check(
            location_simulation_new(session.server, &session.location),
            message: "無法開啟定位模擬服務。"
        )
        connection = session
        return session
#endif
    }

    private static func check(_ error: UnsafeMutablePointer<IdeviceFfiError>?, message: String) throws {
        guard let error else { return }
        defer { idevice_error_free(error) }
        throw Failure.service(message, error.pointee.code, error.pointee.sub_code)
    }

    private final class Connection {
        var adapter: OpaquePointer?
        var handshake: OpaquePointer?
        var server: OpaquePointer?
        var location: OpaquePointer?

        deinit {
            location_simulation_free(location)
            remote_server_free(server)
            rsd_handshake_free(handshake)
            adapter_free(adapter)
        }
    }

    private enum Failure: LocalizedError {
        case requiresIPhone
        case missingPairing
        case pairingFileSize
        case service(String, Int32, Int32)

        var errorDescription: String? {
            switch self {
            case .requiresIPhone: "請在實體 iPhone 上測試定位模擬。"
            case .missingPairing: "請先匯入這支 iPhone 的配對紀錄。"
            case .pairingFileSize: "配對檔案空白或超過 1 MB。"
            case let .service(message, code, subcode): "\(message)（\(code)/\(subcode)）"
            }
        }
    }
}
