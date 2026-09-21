package ai.lumiface.lumiface

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Runs the real MediaCodec on the phone: 30 NV21 frames in sensor orientation (a white disc that
 * moves right on a grey field, the way a portrait phone delivers a landscape sensor image) go in,
 * Annex-B access units come out and are written to the app's files dir for the server-side decoder
 * to check (`adb pull`, then `scripts/check_h264.py`).
 */
@RunWith(AndroidJUnit4::class)
class H264EncoderTest {
    private fun nv21(width: Int, height: Int, discX: Int, discY: Int): ByteArray {
        val bytes = ByteArray(width * height * 3 / 2)
        for (y in 0 until height) for (x in 0 until width) {
            val inside = (x - discX) * (x - discX) + (y - discY) * (y - discY) < 40 * 40
            bytes[y * width + x] = (if (inside) 235 else 80).toByte()
        }
        val uv = width * height
        for (i in 0 until width * height / 2) bytes[uv + i] = 128.toByte()
        return bytes
    }

    @Test
    fun encodesRotatedFramesIntoAnnexBUnits() {
        val width = 1280
        val height = 720
        val frame0 = Frame(nv21(width, height, 200, 360), width, height, width, "nv21", 90)
        val (w, h) = H264Encoder.sizeFor(frame0)
        assertEquals(360, w)
        assertEquals(640, h)
        val encoder = H264Encoder(w, h)
        val chunks = ArrayList<Chunk>()
        for (i in 0 until 30) {
            val f = Frame(nv21(width, height, 200 + i * 20, 360), width, height, width, "nv21", 90)
            chunks.addAll(encoder.encode(f, false, 1000L + i * 66))
        }
        chunks.addAll(encoder.finish())
        assertEquals(30, chunks.size)
        assertEquals(1000L, chunks[0].ts)
        assertTrue("first unit starts with a start code", chunks[0].data[0] == 0.toByte() && chunks[0].data[3] == 1.toByte())
        assertTrue("first unit carries SPS (NAL type 7)", (chunks[0].data[4].toInt() and 0x1f) == 7)
        val dir = InstrumentationRegistry.getInstrumentation().targetContext.filesDir
        val out = File(dir, "h264_test.bin")
        out.outputStream().use { s ->
            for (c in chunks) {
                s.write(java.nio.ByteBuffer.allocate(12).putLong(c.ts).putInt(c.data.size).array())
                s.write(c.data)
            }
        }
        assertTrue(out.length() > 2_000)
    }
}
