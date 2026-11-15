"""Compile actual policy/manager and run JVM tests without native APK builds.
Requires existing Kotlin/JUnit Gradle cache and fixed org.json test jar.
Writes only to a new output directory; never changes caches/dependencies.
"""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('gradle-cache','jdk','json-jar','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 root=Path(__file__).resolve().parents[2];cache=a.gradle_cache
 def jar(pattern):
  files=sorted(cache.glob(pattern));assert files,pattern;return str(files[-1].resolve())
 compiler=jar('org.jetbrains.kotlin/kotlin-compiler-embeddable/2.1.20/*/*.jar')
 stdlib=jar('org.jetbrains.kotlin/kotlin-stdlib/2.1.0/*/*.jar')
 deps=[compiler,stdlib,jar('org.jetbrains.kotlin/kotlin-script-runtime/*/*/*.jar'),jar('org.jetbrains.kotlin/kotlin-reflect/*/*/*.jar'),jar('org.jetbrains.intellij.deps/trove4j/*/*/*.jar'),jar('org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.8.0/*/*.jar'),jar('org.jetbrains/annotations/*/*/*.jar')]
 junit=jar('junit/junit/4.13.2/*/*.jar');hamcrest=jar('org.hamcrest/hamcrest-core/*/*/*.jar')
 java=str(a.jdk/'bin/java.exe');javac=str(a.jdk/'bin/javac.exe');classes=out/'classes';classes.mkdir()
 jsonjar=str(a.json_jar.resolve());cp=os.pathsep.join([str(classes),jsonjar,stdlib,junit,hamcrest])
 commands=[
 [javac,'-encoding','UTF-8','-cp',jsonjar,'-d',str(classes),*[str(root/f) for f in ('app/src/main/java/ai/chloe/voicelab/conversation/GroundedConversationPolicy.java','app/src/main/java/ai/chloe/voicelab/conversation/ReplyEconomyPolicy.java','app/src/main/java/ai/chloe/voicelab/conversation/ReplyIntegrityPolicy.java')]],
 [java,'-cp',os.pathsep.join(deps),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',cp,'-d',str(classes),*[str(root/f) for f in ('app/src/main/java/ai/chloe/voicelab/conversation/ConversationEngine.kt','app/src/test/java/ai/chloe/voicelab/conversation/ConversationTest.kt','app/src/test/java/ai/chloe/voicelab/conversation/GroundedConversationPolicyTest.kt','app/src/test/java/ai/chloe/voicelab/conversation/ReplyEconomyPolicyTest.kt','app/src/test/java/ai/chloe/voicelab/conversation/ReplyIntegrityPolicyTest.kt')]],
 [java,'-cp',cp,'org.junit.runner.JUnitCore','ai.chloe.voicelab.conversation.ConversationTest','ai.chloe.voicelab.conversation.GroundedConversationPolicyTest','ai.chloe.voicelab.conversation.ReplyEconomyPolicyTest','ai.chloe.voicelab.conversation.ReplyIntegrityPolicyTest']]
 for i,cmd in enumerate(commands):
  r=subprocess.run(cmd,cwd=root/'app',capture_output=True,text=True,encoding='utf-8',errors='replace');(out/f'step-{i}.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0,('step',i,r.returncode)
 (out/'checks.json').write_text(json.dumps({'java_policy_and_actual_kotlin_manager_compiled':True,'junit_exit_code':0,'json_jar_sha256':hashlib.sha256(a.json_jar.read_bytes()).hexdigest()},indent=2),encoding='utf-8')
if __name__=='__main__':main()
