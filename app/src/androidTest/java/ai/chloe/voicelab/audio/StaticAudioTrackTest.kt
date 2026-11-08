package ai.chloe.voicelab.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Device regression: static tracks become initialized only after PCM has been written. */
@RunWith(AndroidJUnit4::class)
class StaticAudioTrackTest {
    @Test fun initializesAfterFirstPcmWrite() {
        val pcm = ByteArray(24000 * 2)
        val track = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(24000)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
            .setTransferMode(AudioTrack.MODE_STATIC).setBufferSizeInBytes(pcm.size).build()
        try {
            assertEquals(AudioTrack.STATE_NO_STATIC_DATA, track.state)
            assertEquals(pcm.size, track.write(pcm, 0, pcm.size, AudioTrack.WRITE_BLOCKING))
            assertEquals(AudioTrack.STATE_INITIALIZED, track.state)
        } finally { track.release() }
    }
}
