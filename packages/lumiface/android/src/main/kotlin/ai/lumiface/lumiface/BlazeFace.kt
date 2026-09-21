package ai.lumiface.lumiface

import android.content.Context
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel
import kotlin.math.ceil
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import org.tensorflow.lite.Interpreter

/** One camera frame as the Dart side sends it: NV21 bytes in sensor orientation plus the rotation that makes them upright. */
class Frame(val bytes: ByteArray, val width: Int, val height: Int, val bytesPerRow: Int, val format: String, val rotation: Int)

/**
 * BlazeFace short range (MediaPipe `face_detection_short_range.tflite`): a 128x128 input, 896 anchors, a score and a box per anchor. The frame is rotated
 * upright and letterboxed while it is sampled into the input, so the boxes come out in upright,
 * frame-normalised coordinates. Decoding follows MediaPipe's anchor and tensors-to-detections options.
 */
class BlazeFace(context: Context) {
    private val interpreter: Interpreter
    private val input = ByteBuffer.allocateDirect(INPUT * INPUT * 3 * 4).order(ByteOrder.nativeOrder())
    private val boxes = Array(1) { Array(ANCHORS) { FloatArray(16) } }
    private val scores = Array(1) { Array(ANCHORS) { FloatArray(1) } }
    private val boxesIndex: Int

    init {
        val fd = context.assets.openFd("face_detection_short_range.tflite")
        val model = fd.createInputStream().channel.map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
        interpreter = Interpreter(model, Interpreter.Options().setNumThreads(2))
        boxesIndex = if (interpreter.getOutputTensor(0).shape().last() == 16) 0 else 1
    }

    fun detect(f: Frame): List<Map<String, Double>> {
        val rotated = f.rotation == 90 || f.rotation == 270
        val uw = if (rotated) f.height else f.width
        val uh = if (rotated) f.width else f.height
        val scale = INPUT.toFloat() / max(uw, uh)
        val padX = (INPUT - uw * scale) / 2f
        val padY = (INPUT - uh * scale) / 2f
        fill(f, uw, uh, scale, padX, padY)
        interpreter.runForMultipleInputsOutputs(arrayOf(input), mapOf(boxesIndex to boxes, 1 - boxesIndex to scores))
        return decode(padX / INPUT, padY / INPUT)
    }

    private fun fill(f: Frame, uw: Int, uh: Int, scale: Float, padX: Float, padY: Float) {
        input.rewind()
        val ySize = f.bytesPerRow * f.height
        for (oy in 0 until INPUT) {
            val uy = ((oy + 0.5f - padY) / scale).toInt()
            for (ox in 0 until INPUT) {
                val ux = ((ox + 0.5f - padX) / scale).toInt()
                if (ux < 0 || uy < 0 || ux >= uw || uy >= uh) {
                    input.putFloat(-1f); input.putFloat(-1f); input.putFloat(-1f)
                    continue
                }
                val rx: Int
                val ry: Int
                when (f.rotation) {
                    90 -> { rx = uy; ry = f.height - 1 - ux }
                    180 -> { rx = f.width - 1 - ux; ry = f.height - 1 - uy }
                    270 -> { rx = f.width - 1 - uy; ry = ux }
                    else -> { rx = ux; ry = uy }
                }
                val y = (f.bytes[ry * f.bytesPerRow + rx].toInt() and 0xff) - 16
                val uv = ySize + (ry / 2) * f.bytesPerRow + (rx / 2) * 2
                val v = (f.bytes[uv].toInt() and 0xff) - 128
                val u = (f.bytes[uv + 1].toInt() and 0xff) - 128
                val yy = 1.164f * max(y, 0)
                input.putFloat(clamp(yy + 1.596f * v) / 127.5f - 1f)
                input.putFloat(clamp(yy - 0.392f * u - 0.813f * v) / 127.5f - 1f)
                input.putFloat(clamp(yy + 2.017f * u) / 127.5f - 1f)
            }
        }
    }

    private fun decode(fx: Float, fy: Float): List<Map<String, Double>> {
        val sx = 1 - 2 * fx
        val sy = 1 - 2 * fy
        val found = ArrayList<Detection>()
        for (i in 0 until ANCHORS) {
            val logit = min(100f, max(-100f, scores[0][i][0]))
            val score = 1f / (1f + exp(-logit))
            if (score < SCORE_THRESHOLD) continue
            val b = boxes[0][i]
            val cx = b[0] / INPUT + anchors[i * 2]
            val cy = b[1] / INPUT + anchors[i * 2 + 1]
            val w = b[2] / INPUT
            val h = b[3] / INPUT
            found.add(Detection(score, (cx - w / 2 - fx) / sx, (cy - h / 2 - fy) / sy, w / sx, h / sy))
        }
        found.sortByDescending { it.score }
        val kept = ArrayList<Detection>()
        for (d in found) if (kept.all { iou(it, d) < NMS_IOU }) kept.add(d)
        return kept.map {
            mapOf("left" to it.left.toDouble(), "top" to it.top.toDouble(), "width" to it.width.toDouble(), "height" to it.height.toDouble())
        }
    }

    fun close() = interpreter.close()

    private class Detection(val score: Float, val left: Float, val top: Float, val width: Float, val height: Float)

    companion object {
        const val INPUT = 128
        const val ANCHORS = 896
        private const val SCORE_THRESHOLD = 0.5f
        private const val NMS_IOU = 0.3f
        private val STRIDES = intArrayOf(8, 16, 16, 16)

        /** 512 anchor centres on the 16x16 map (two per cell), then 384 on the 8x8 map (six per cell), as x, y pairs. */
        private val anchors: FloatArray by lazy {
            val out = FloatArray(ANCHORS * 2)
            var n = 0
            var layer = 0
            while (layer < STRIDES.size) {
                val stride = STRIDES[layer]
                var perCell = 0
                var last = layer
                while (last < STRIDES.size && STRIDES[last] == stride) { perCell += 2; last++ }
                val cells = ceil(INPUT / stride.toDouble()).toInt()
                for (y in 0 until cells) for (x in 0 until cells) repeat(perCell) {
                    out[n++] = (x + 0.5f) / cells
                    out[n++] = (y + 0.5f) / cells
                }
                layer = last
            }
            out
        }

        private fun clamp(v: Float) = min(255f, max(0f, v))

        private fun iou(a: Detection, b: Detection): Float {
            val x1 = max(a.left, b.left)
            val y1 = max(a.top, b.top)
            val x2 = min(a.left + a.width, b.left + b.width)
            val y2 = min(a.top + a.height, b.top + b.height)
            val inter = max(0f, x2 - x1) * max(0f, y2 - y1)
            val union = a.width * a.height + b.width * b.height - inter
            return if (union <= 0f) 0f else inter / union
        }
    }
}
