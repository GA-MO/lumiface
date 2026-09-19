package ai.lumiface.lumiface

import android.os.Handler
import android.os.Looper
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.Executors

/**
 * `ai.lumiface/detector`: runs BlazeFace (TensorFlow Lite, bundled) on every camera frame the Dart side
 * sends and, while recording, feeds the same frame to the H.264 encoder. `process` answers with the
 * faces and the access units the encoder has finished; `stopRecording` flushes it.
 */
class LumifacePlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
    private lateinit var channel: MethodChannel
    private var detector: BlazeFace? = null
    private var encoder: H264Encoder? = null
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel = MethodChannel(binding.binaryMessenger, "ai.lumiface/detector")
        channel.setMethodCallHandler(this)
        detector = BlazeFace(binding.applicationContext)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
        executor.execute {
            encoder?.finish()
            encoder = null
        }
        detector?.close()
        detector = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "process" -> process(call, result)
            "stopRecording" -> executor.execute {
                val out = try {
                    encoder?.finish() ?: emptyList()
                } catch (e: Exception) {
                    emptyList()
                }
                encoder = null
                main.post { result.success(out.map { chunk(it) }) }
            }
            else -> result.notImplemented()
        }
    }

    private fun process(call: MethodCall, result: MethodChannel.Result) {
        val bytes = call.argument<ByteArray>("bytes")!!
        val width = call.argument<Int>("width")!!
        val height = call.argument<Int>("height")!!
        val bytesPerRow = call.argument<Int>("bytesPerRow")!!
        val format = call.argument<String>("format")!!
        val rotation = call.argument<Int>("rotation")!!
        val mirror = call.argument<Boolean>("mirror") ?: false
        val ts = (call.argument<Number>("ts") ?: 0).toLong()
        val record = call.argument<Boolean>("record") ?: false
        val d = detector
        if (d == null) {
            result.error("DETECTOR_UNAVAILABLE", "plugin detached", null)
            return
        }
        executor.execute {
            try {
                val frame = Frame(bytes, width, height, bytesPerRow, format, rotation)
                val faces = d.detect(frame)
                val chunks = if (record) {
                    val enc = encoder ?: H264Encoder.sizeFor(frame).let { (w, h) -> H264Encoder(w, h) }.also { encoder = it }
                    enc.encode(frame, mirror, ts).map { chunk(it) }
                } else emptyList()
                main.post { result.success(mapOf("faces" to faces, "chunks" to chunks)) }
            } catch (e: Exception) {
                main.post { result.error("DETECT_FAILED", e.message, null) }
            }
        }
    }

    private fun chunk(c: Chunk) = mapOf("ts" to c.ts, "data" to c.data)
}
