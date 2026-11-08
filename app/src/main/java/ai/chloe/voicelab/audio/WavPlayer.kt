package ai.chloe.voicelab.audio

import android.content.Context
import android.media.*
import kotlinx.coroutines.*
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Plays our fixed PCM16/mono WAV. Timestamp is Android output timing, not an acoustic measurement. */
internal class WavPlayer(context: Context, private val scope: CoroutineScope) {
    private val manager = context.getSystemService(AudioManager::class.java)
    private var job: Job? = null
    private val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
    private val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
        .setAudioAttributes(attributes)
        .setOnAudioFocusChangeListener { if (it < 0) stop() }.build()

    fun play(file: File, onFirstFrame: (Long) -> Unit, onFinished: (String?) -> Unit) {
        val previous = job
        job = scope.launch(Dispatchers.IO) {
            previous?.cancelAndJoin()
            var track: AudioTrack? = null
            var error: String? = null
            try {
                check(manager.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) { "오디오 포커스를 얻지 못했습니다." }
                val wav = file.readBytes()
                check(wav.size > 44 && String(wav, 0, 4) == "RIFF" && String(wav, 36, 4) == "data") { "지원하지 않는 WAV" }
                val header = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
                check(header.getShort(20).toInt() == 1 && header.getShort(22).toInt() == 1 && header.getShort(34).toInt() == 16)
                val rate = header.getInt(24)
                check(rate == 24000 && header.getInt(40) == wav.size - 44)
                val pcmSize = wav.size - 44
                track = AudioTrack.Builder().setAudioAttributes(attributes)
                    .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(rate).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                    .setTransferMode(AudioTrack.MODE_STATIC).setBufferSizeInBytes(pcmSize).build()
                check(track.state == AudioTrack.STATE_INITIALIZED) { "AudioTrack 초기화 실패" }
                check(track.write(wav, 44, pcmSize, AudioTrack.WRITE_BLOCKING) == pcmSize) { "PCM 쓰기 실패" }
                ensureActive()
                track.play()
                val timestamp = AudioTimestamp()
                var firstReported = false
                val start = System.nanoTime()
                while (track.playbackHeadPosition.toLong().and(0xffffffffL) < pcmSize / 2L) {
                    ensureActive()
                    if (!firstReported && track.getTimestamp(timestamp) && timestamp.framePosition > 0) {
                        val firstNanos = timestamp.nanoTime - (timestamp.framePosition - 1) * 1_000_000_000L / rate
                        firstReported = true
                        withContext(Dispatchers.Main) { onFirstFrame(firstNanos) }
                    }
                    check(System.nanoTime() - start < (pcmSize / 2.0 / rate * 1e9 + 5e9)) { "WAV 재생 시간 초과" }
                    delay(10)
                }
            } catch (e: CancellationException) { throw e }
              catch (e: Exception) { error = e.message ?: e.javaClass.simpleName }
            finally {
                runCatching { track?.stop() }; track?.release()
                manager.abandonAudioFocusRequest(focus)
                withContext(NonCancellable + Dispatchers.Main) { onFinished(error) }
            }
        }
    }
    fun stop() { job?.cancel(); job = null }
}
