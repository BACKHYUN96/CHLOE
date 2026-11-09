package ai.chloe.voicelab.comparison

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

class ComparisonActivity : ComponentActivity() {
    private val vm: ComparisonViewModel by viewModels()
    private val modelImport = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { it?.let { uri -> vm.importFolder(uri,true) } }
    private val sampleImport = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { it?.let { uri -> vm.importFolder(uri,false) } }
    private val wavExport = registerForActivityResult(ActivityResultContracts.CreateDocument("audio/wav")) { it?.let { uri -> vm.export(uri,"wav") } }
    private val reportExport = registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { it?.let { uri -> vm.export(uri,"metrics") } }
    private val blindExport = registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { it?.let { uri -> vm.export(uri,"blind") } }
    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState)
        setContent { MaterialTheme {
            val s by vm.state.collectAsStateWithLifecycle()
            DisposableEffect(s.busy) {
                if(s.busy)window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                onDispose { window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
            }
            LazyColumn(Modifier.fillMaxSize().safeDrawingPadding(),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                item {
                    Text("CHLOE TTS Lab",style=MaterialTheme.typography.headlineMedium)
                    Row { TextButton(onClick={ finish() },enabled=!s.busy){Text("기존 Voice Lab")}
                        TextButton(onClick={vm.setBlind(!s.blind)},enabled=!s.busy&&!s.playing){Text(if(s.blind)"생성·측정 화면" else "A/B 블라인드 청취")} }
                    Text(s.status);s.error?.let{Text(it,color=MaterialTheme.colorScheme.error)}
                    if(s.busy&&!s.importing || s.playing)OutlinedButton(onClick=vm::stop){Text(if(s.playing)"재생 중지" else "실험 중지")}
                }
                if(s.blind) {
                    item {
                        Text("모델 이름은 정답 공개 전 숨깁니다. 같은 문장·조건·seed·플랫폼끼리 비교합니다.")
                        LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            itemsIndexed(vm.cases) { index,c -> FilterChip(selected=s.caseIndex==index,onClick={vm.chooseCase(index)},enabled=!s.playing,label={Text(c.id)}) }
                        }
                        Text(vm.cases[s.caseIndex].text)
                        Row { listOf("controlled" to "공통 조건","optimized" to "모델별 조정").forEach { (key,label) -> FilterChip(selected=s.blindCondition==key,onClick={vm.blindCondition(key)},enabled=!s.playing,label={Text(label)}) } }
                        Button(onClick=vm::newPair,enabled=!s.playing){Text("무작위 A/B 선택")}
                        Text(s.pairText)
                    }
                    if(s.hasPair) {
                        items(2) { side ->
                            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(12.dp)) {
                                Text(if(side==0)"음성 A" else "음성 B",style=MaterialTheme.typography.titleLarge)
                                if(s.revealed) { Text(vm.identity(side)); Text(vm.auxiliary(side)) }
                                Button(onClick={vm.play(side)},enabled=!s.playing){Text("재생")}
                                dimensions.forEachIndexed { dimension,label ->
                                    Text(label)
                                    Row { (1..5).forEach { score ->
                                        FilterChip(selected=s.scores[side][dimension]==score,onClick={vm.score(side,dimension,score)},label={Text("$score")})
                                    } }
                                }
                                val rated=s.scores[side].filter{it>0}
                                Text(if(rated.isEmpty())"미평가" else "입력 ${rated.size}/6 · 평균 %.2f".format(rated.average()))
                            } }
                        }
                        item {
                            Text("점수는 기기 내부에 자동 저장합니다. 1 낮음 · 5 높음 · 미입력은 미평가입니다.")
                            OutlinedTextField(value=s.notes,onValueChange=vm::notes,label={Text("문장 끝·쉼·강세·감정 메모")},modifier=Modifier.fillMaxWidth())
                            OutlinedButton(onClick=vm::reveal,enabled=!s.revealed){Text("정답 공개 · 이후 평가는 공개 상태로 기록")}
                            Button(onClick={blindExport.launch("chloe-blind-evaluations.json")}){Text("청취 평가 JSON 내보내기")}
                        }
                    }
                } else {
                    item { Text("모델 실행 가능 여부",style=MaterialTheme.typography.titleLarge) }
                    items(comparisonModels.size) { i ->
                        val model=comparisonModels[i]
                        Card { Column(Modifier.padding(12.dp)) {
                            Text(model)
                            Text(when(model){CUSTOM->if(vm.available(model))"기존 Sohee 1.7B 사용 가능" else "기존 Voice Lab에서 1.7B를 가져오세요"
                                DESIGN->if(s.designInstalled)"실험 모델 설치됨 · 기기 검증 필요" else "별도 VoiceDesign 모델 가져오기 필요"
                                "openbmb/VoxCPM2"->"공식 Android 경로 확인 · CHLOE 실행 미연결 · PC 샘플 가져오기 가능"
                                else->"공식 한국어 지원 · CHLOE Android 실행 미연결 · PC 샘플 가져오기 가능"})
                            FilterChip(selected=s.model==model,onClick={vm.chooseModel(model)},enabled=!s.busy&&!s.playing,label={Text("선택")})
                        } }
                    }
                    item {
                        Row { TextButton(onClick={modelImport.launch(null)},enabled=!s.busy&&!s.playing&&!s.designInstalled){Text("VoiceDesign 폴더 가져오기")}
                            TextButton(onClick={sampleImport.launch(null)},enabled=!s.busy&&!s.playing){Text("PC 샘플 폴더 가져오기")} }
                        Text("입력 문장",style=MaterialTheme.typography.titleLarge)
                        LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            itemsIndexed(vm.cases) { index,c -> FilterChip(selected=s.caseIndex==index,onClick={vm.chooseCase(index)},enabled=!s.busy,label={Text(c.id)}) }
                        }
                        Text(vm.cases[s.caseIndex].group+" · "+vm.cases[s.caseIndex].text)
                        OutlinedTextField(value=s.instruction,onValueChange=vm::instruction,enabled=!s.busy,label={Text("스타일 지시 · VoiceDesign은 여성 음색 설명 포함")},modifier=Modifier.fillMaxWidth())
                        LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            itemsIndexed(vm.referenceStyles) { _,ref -> FilterChip(selected=s.referenceId==ref.id,onClick={vm.applyStyle(ref.id)},enabled=!s.busy,label={Text(ref.label)}) }
                        }
                        Row { listOf("controlled" to "공통 조건","optimized" to "모델별 조정").forEach { (key,label) -> FilterChip(selected=s.condition==key,onClick={vm.condition(key)},enabled=!s.busy,label={Text(label)}) } }
                        Row { listOf(42,43,44).forEach { seed -> FilterChip(selected=s.seed==seed,onClick={vm.seed(seed)},enabled=!s.busy,label={Text("seed $seed")}) } }
                        Text("동일 seed가 서로 다른 모델의 동일 난수를 의미하지 않습니다. VoiceDesign은 Sohee가 아니며 음색 설명이 추가됩니다.")
                        Row {
                            Button(onClick={vm.generate(false)},enabled=vm.available(s.model)&&!s.busy&&!s.playing){Text("한 문장 생성")}
                            OutlinedButton(onClick={vm.generate(true)},enabled=vm.available(s.model)&&!s.busy&&!s.playing){Text("20문장 × 3회")}
                        }
                        OutlinedButton(onClick={vm.generate(false,10)},enabled=vm.available(s.model)&&!s.busy&&!s.playing){Text("같은 문장·seed 10회 안정성 측정")}
                        Text("연속 합성은 통화 부하의 대리 시험이며 실제 통화 지속 성능 측정이 아닙니다. 60회 연속 합성은 오래 걸릴 수 있습니다. 높은 열 상태에서는 다음 실행을 멈추고 완료된 WAV와 오류는 보존합니다. 모델·원음은 서버로 전송하지 않습니다.")
                        Text(s.metrics);Text("저장된 비교 샘플 ${s.records}개")
                        Row { Button(onClick={vm.play()},enabled=s.hasOutput&&!s.busy&&!s.playing){Text("마지막 WAV 재생")}
                            TextButton(onClick={wavExport.launch("chloe-comparison.wav")},enabled=s.hasOutput&&!s.busy){Text("WAV 내보내기")} }
                        Button(onClick={reportExport.launch("chloe-comparison-metrics.json")},enabled=!s.busy){Text("성능·출처 JSON 내보내기")}
                        Text("첫 PCM 준비·수동 재생 타임스탬프와 실제 스피커 도달 시간은 별개입니다. GPU 사용률·지속 통화 저하는 미측정이며, 이번 엔진은 문장 전체 생성 후 재생합니다.")
                    }
                }
            }
        } }
    }
    override fun onStop() { if(!isChangingConfigurations && (vm.state.value.busy&&!vm.state.value.importing || vm.state.value.playing))vm.stop();super.onStop() }
}
