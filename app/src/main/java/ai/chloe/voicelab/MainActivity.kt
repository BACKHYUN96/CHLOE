package ai.chloe.voicelab

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ai.chloe.voicelab.lab.*
import ai.chloe.voicelab.model.ModelSpec

class MainActivity : ComponentActivity() {
    private val vm: LabViewModel by viewModels()
    private val importFolder = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri -> uri?.let(vm::importModels) }
    private val exportWav = registerForActivityResult(ActivityResultContracts.CreateDocument("audio/wav")) { uri -> uri?.let { vm.export(it, "wav") } }
    private val exportReport = registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let { vm.export(it, "json") } }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Color(0xFF625783), background = Color(0xFFF8F6FC))) {
                val state by vm.state.collectAsStateWithLifecycle()
                LabScreen(state, vm,
                    onImport = { importFolder.launch(null) },
                    onExportWav = { exportWav.launch("chloe-sohee.wav") },
                    onExportReport = { vm.saveEvaluation(); exportReport.launch("chloe-evaluation.json") })
            }
        }
    }
    override fun onStop() {
        // File pickers also stop the activity; no background synthesis is needed for alpha1.
        if (!isChangingConfigurations && (vm.state.value.busy && !vm.state.value.importing || vm.state.value.playing)) vm.stop()
        super.onStop()
    }
}

@Composable
private fun LabScreen(s: LabState, vm: LabViewModel, onImport: () -> Unit, onExportWav: () -> Unit, onExportReport: () -> Unit) {
    var samplesExpanded by remember { mutableStateOf(false) }
    LazyColumn(
        modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding(),
        contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Text("CHLOE", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
            Text("Voice Lab", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(8.dp))
            Text("한국어 여성 음성 실험실 · ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodyMedium)
            Text("완전 오프라인 · Sohee · ${s.model.label} CustomVoice", style = MaterialTheme.typography.labelLarge)
        }
        item {
            LabCard("모델") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ModelSpec.entries.forEach { spec ->
                        FilterChip(selected = s.model == spec, onClick = { vm.selectModel(spec) },
                            enabled = !s.busy && !s.playing,
                            label = { Text("${spec.label} · ${if (spec in s.installedModels) "설치됨" else "미설치"}") })
                    }
                }
                Text(if (s.installed) "${s.model.label} F16 패키지 설치됨" else "${s.model.label} 모델 폴더를 가져오세요.")
                Text("model-pack.json과 GGUF 두 파일이 있는 폴더를 선택하세요. 가져온 파일은 앱 내부 저장소에 복사됩니다.", style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onImport, enabled = !s.busy && !s.ready) { Text("폴더 가져오기") }
                    Button(onClick = vm::initialize, enabled = s.installed && !s.busy && !s.ready) { Text("초기화") }
                }
                Text("두 모델을 별도 보관합니다. 모델 선택을 바꾸면 기존 추론 메모리를 해제하며 다시 초기화해야 합니다.", style = MaterialTheme.typography.bodySmall)
                if (s.model == ModelSpec.LARGE) Text("1.7B는 기기 성능·메모리·음질 검증 전입니다. 먼저 짧은 문장으로 시험하세요.", style = MaterialTheme.typography.bodySmall)
            }
        }
        item {
            LabCard("음성 생성") {
                OutlinedTextField(value = s.text, onValueChange = vm::setText, modifier = Modifier.fillMaxWidth(),
                    enabled = !s.busy, label = { Text("한국어 문장") }, minLines = 3, maxLines = 6,
                    supportingText = { Text("${s.text.codePointCount(0, s.text.length)} / 240자") })
                if (s.model.supportsInstruction) OutlinedTextField(value = s.instruction, onValueChange = vm::setInstruction,
                    enabled = !s.busy, modifier = Modifier.fillMaxWidth(), maxLines = 3,
                    label = { Text("말투 지시 (선택 · 1.7B)") },
                    placeholder = { Text("차분하고 다정하게, 친한 친구에게 말하듯") },
                    supportingText = { Text("${s.instruction.codePointCount(0, s.instruction.length)} / 240자 · 비워 두면 기본 Sohee") })
                Row {
                    Checkbox(checked = s.autoPlay, onCheckedChange = vm::setAutoPlay, enabled = !s.busy)
                    Text("생성 후 자동 재생", modifier = Modifier.padding(top = 12.dp))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = vm::generate, enabled = s.ready && !s.busy && !s.playing) { Text("합성 시작") }
                    OutlinedButton(onClick = { vm.play() }, enabled = s.hasAudio && !s.busy && !s.playing) { Text("재생") }
                    OutlinedButton(onClick = vm::stop, enabled = s.ready || s.busy || s.playing) { Text("중지") }
                }
                Text("${s.model.label} · F16 + 일부 F32 안정화 · CPU 4 스레드\n문장 전체 생성 후 재생합니다. ${if (s.model.supportsInstruction) "1.7B는 말투 지시를 사용할 수 있습니다." else "0.6B는 자연어 감정 지시를 지원하지 않습니다."}", style = MaterialTheme.typography.bodySmall)
            }
        }
        item {
            LabCard("상태 및 측정") {
                if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                Text(s.status, fontWeight = FontWeight.Medium)
                s.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                Text(s.memory, style = MaterialTheme.typography.bodySmall)
                HorizontalDivider()
                Text(s.metrics)
                Text("RTF = 생성 시간 ÷ 오디오 길이. 1보다 작으면 실시간보다 빠릅니다.\n첫 재생 출력은 자동 재생 시 AudioTrack 타임스탬프 기준입니다. 기기에서 값을 제공하지 않으면 미측정으로 남습니다. 스피커 소리의 물리적 도달 시간은 별도 측정이 필요합니다.", style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = onExportWav, enabled = s.hasAudio && !s.busy) { Text("WAV 내보내기") }
                    TextButton(onClick = onExportReport, enabled = s.hasReport && !s.busy) { Text("측정 JSON") }
                }
            }
        }
        if (s.hasReport) item {
            LabCard("이 문장 청취 평가") {
                Text("1 낮음 · 5 높음 · 선택 전에는 미평가", style = MaterialTheme.typography.bodySmall)
                Score("발음", s.pronunciation) { vm.rate("pronunciation", it) }
                Score("억양", s.intonation) { vm.rate("intonation", it) }
                Score("리듬 / 자연스러움", s.rhythm) { vm.rate("rhythm", it) }
                OutlinedTextField(s.notes, vm::notes, label = { Text("관찰 메모") }, modifier = Modifier.fillMaxWidth(), maxLines = 4)
                Button(onClick = vm::saveEvaluation, enabled = !s.busy) { Text("평가 저장") }
                Text("각 생성의 문장·측정·평가는 내부 저장소에 별도 JSON으로 보관됩니다.", style = MaterialTheme.typography.bodySmall)
            }
        }
        item { TextButton(onClick = { samplesExpanded = !samplesExpanded }) { Text(if (samplesExpanded) "기본 테스트 10문장 접기" else "기본 테스트 10문장 열기") } }
        if (samplesExpanded) itemsIndexed(koreanSamples) { index, sample ->
            OutlinedCard(onClick = { vm.setText(sample) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                Text("${index + 1}. $sample", Modifier.padding(16.dp))
            }
        }
        item { Text("S26 Ultra에서 발음·지연·발열을 직접 평가하는 실험용 앱입니다. 실기기 음질과 통화 수준의 응답성은 검증 전입니다.", style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun LabCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun Score(label: String, selected: Int, onSelect: (Int) -> Unit) {
    Text(label, style = MaterialTheme.typography.labelLarge)
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        for (score in 1..5) FilterChip(selected == score, onClick = { onSelect(score) }, label = { Text("$score") })
    }
}
