package ai.lumiface.lumiface

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import java.nio.ByteBuffer
import kotlin.math.max
import kotlin.math.roundToInt

/** One encoded access unit and the frame time (device ms) it was fed at. */
class Chunk(val ts: Long, val data: ByteArray)

/**
 * MediaCodec H.264 (baseline, no B-frames) fed with the camera frame rotated upright, un-mirrored and
 * scaled to a 640 px long side. Every output is one Annex-B access unit with the parameter sets in
 * front of each keyframe, so the server can decode any chunk from the last keyframe on. Frames keep
 * the device time they were fed at as their presentation time, which comes back on the chunk.
 */
class H264Encoder(private val width: Int, private val height: Int) {
    private val codec: MediaCodec = MediaCodec.createEncoderByType(MIME)
    private var config: ByteArray? = null
    private val info = MediaCodec.BufferInfo()

    init {
        val format = MediaFormat.createVideoFormat(MIME, width, height).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible)
            setInteger(MediaFormat.KEY_BIT_RATE, BIT_RATE)
            setInteger(MediaFormat.KEY_FRAME_RATE, FRAME_RATE)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
            setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
            setInteger(MediaFormat.KEY_LEVEL, MediaCodecInfo.CodecProfileLevel.AVCLevel31)
        }
        try {
            codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        } catch (e: Exception) {
            format.setString(MediaFormat.KEY_PROFILE, null)
            format.setString(MediaFormat.KEY_LEVEL, null)
            codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        }
        codec.start()
    }

    /** Feeds one frame (sampled from the raw NV21 through `f`'s rotation) and returns what the encoder has finished. */
    fun encode(f: Frame, mirror: Boolean, ts: Long): List<Chunk> {
        val index = codec.dequeueInputBuffer(10_000)
        if (index >= 0) {
            val image = codec.getInputImage(index)
            if (image != null) {
                fill(image, f, mirror)
                codec.queueInputBuffer(index, 0, image.planes[0].rowStride * height * 3 / 2, ts * 1000, 0)
            } else {
                codec.queueInputBuffer(index, 0, 0, ts * 1000, 0)
            }
        }
        return drain(false)
    }

    /** Flushes the encoder and returns the last access units. */
    fun finish(): List<Chunk> {
        val index = codec.dequeueInputBuffer(50_000)
        if (index >= 0) codec.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
        val out = drain(true)
        codec.stop()
        codec.release()
        return out
    }

    private fun fill(image: android.media.Image, f: Frame, mirror: Boolean) {
        val rotated = f.rotation == 90 || f.rotation == 270
        val uw = if (rotated) f.height else f.width
        val uh = if (rotated) f.width else f.height
        val ySize = f.bytesPerRow * f.height
        val y = image.planes[0]
        val u = image.planes[1]
        val v = image.planes[2]
        val yBuf = y.buffer
        val uBuf = u.buffer
        val vBuf = v.buffer
        for (oy in 0 until height) {
            val sy = (oy.toLong() * uh / height).toInt()
            for (ox in 0 until width) {
                var sx = (ox.toLong() * uw / width).toInt()
                if (mirror) sx = uw - 1 - sx
                val rx: Int
                val ry: Int
                when (f.rotation) {
                    90 -> { rx = sy; ry = f.height - 1 - sx }
                    180 -> { rx = f.width - 1 - sx; ry = f.height - 1 - sy }
                    270 -> { rx = f.width - 1 - sy; ry = sx }
                    else -> { rx = sx; ry = sy }
                }
                yBuf.put(oy * y.rowStride + ox * y.pixelStride, f.bytes[ry * f.bytesPerRow + rx])
                if ((ox and 1) == 0 && (oy and 1) == 0) {
                    val uv = ySize + (ry / 2) * f.bytesPerRow + (rx / 2) * 2
                    val cx = ox / 2
                    val cy = oy / 2
                    vBuf.put(cy * v.rowStride + cx * v.pixelStride, f.bytes[uv])
                    uBuf.put(cy * u.rowStride + cx * u.pixelStride, f.bytes[uv + 1])
                }
            }
        }
    }

    private fun drain(untilEnd: Boolean): List<Chunk> {
        val out = ArrayList<Chunk>()
        while (true) {
            val index = codec.dequeueOutputBuffer(info, if (untilEnd) 50_000 else 0)
            if (index == MediaCodec.INFO_TRY_AGAIN_LATER) {
                if (untilEnd) continue else break
            }
            if (index < 0) continue
            val buffer: ByteBuffer = codec.getOutputBuffer(index) ?: break
            val bytes = ByteArray(info.size)
            buffer.position(info.offset)
            buffer.get(bytes)
            codec.releaseOutputBuffer(index, false)
            if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) {
                config = bytes
            } else if (info.size > 0) {
                val key = info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0
                val cfg = config
                out.add(Chunk(info.presentationTimeUs / 1000, if (key && cfg != null) cfg + bytes else bytes))
            }
            if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
        }
        return out
    }

    companion object {
        const val MIME = "video/avc"
        const val BIT_RATE = 1_500_000
        const val FRAME_RATE = 15
        const val LONG_SIDE = 640

        /** Upright, even-sided encoder size for a frame: the long side scaled to 640 px. */
        fun sizeFor(f: Frame): Pair<Int, Int> {
            val rotated = f.rotation == 90 || f.rotation == 270
            val uw = if (rotated) f.height else f.width
            val uh = if (rotated) f.width else f.height
            val scale = LONG_SIDE.toFloat() / max(uw, uh)
            val w = ((uw * scale).roundToInt() / 2) * 2
            val h = ((uh * scale).roundToInt() / 2) * 2
            return Pair(max(w, 16), max(h, 16))
        }
    }
}
