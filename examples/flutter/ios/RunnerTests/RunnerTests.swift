import CoreVideo
import Flutter
import UIKit
import XCTest
@testable import lumiface

/// Runs the real VideoToolbox encoder on the phone: 30 BGRA frames (a white disc moving right on a grey
/// field) go in mirrored, Annex-B access units come out and are written to Documents for the server-side
/// decoder to check (`xcrun devicectl device copy from`, then the same check as the Android test).
class RunnerTests: XCTestCase {
  private func bgra(width: Int, height: Int, discX: Int, discY: Int) -> Data {
    var data = Data(count: width * height * 4)
    data.withUnsafeMutableBytes { (raw: UnsafeMutableRawBufferPointer) in
      let p = raw.bindMemory(to: UInt8.self)
      for y in 0..<height {
        for x in 0..<width {
          let inside = (x - discX) * (x - discX) + (y - discY) * (y - discY) < 40 * 40
          let v: UInt8 = inside ? 235 : 80
          let i = (y * width + x) * 4
          p[i] = v; p[i + 1] = v; p[i + 2] = v; p[i + 3] = 255
        }
      }
    }
    return data
  }

  func testEncodesMirroredFramesIntoAnnexBUnits() throws {
    let width = 720, height = 1280
    guard let encoder = H264Encoder(width: width, height: height) else { return XCTFail("no encoder") }
    var chunks: [Chunk] = []
    for i in 0..<30 {
      let (buffer, _) = try LumifacePlugin.detect(bytes: bgra(width: width, height: height, discX: 100 + i * 15, discY: 400),
                                                 width: width, height: height, bytesPerRow: width * 4, rotation: 0)
      chunks.append(contentsOf: encoder.encode(buffer, mirror: true, ts: Int64(1000 + i * 66)))
    }
    chunks.append(contentsOf: encoder.finish())
    XCTAssertEqual(chunks.count, 30)
    XCTAssertEqual(chunks[0].ts, 1000)
    XCTAssertEqual(Array(chunks[0].data.prefix(4)), [0, 0, 0, 1])
    XCTAssertEqual(chunks[0].data[4] & 0x1f, 7, "first unit carries SPS")
    var out = Data()
    for c in chunks {
      var ts = c.ts.bigEndian
      var n = Int32(c.data.count).bigEndian
      out.append(Data(bytes: &ts, count: 8))
      out.append(Data(bytes: &n, count: 4))
      out.append(c.data)
    }
    let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("h264_test.bin")
    try out.write(to: url)
    XCTAssertGreaterThan(out.count, 2000)
  }
}
