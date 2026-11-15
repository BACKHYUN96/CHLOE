"""Build the framework-only instrumentation APK; never install over an original."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--jdk', type=Path, required=True)
    parser.add_argument('--keystore', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory, must not exist')
    parser.add_argument('--platform', default='android-36')
    parser.add_argument('--build-tools', default='35.0.0')
    options = parser.parse_args()
    password = os.environ['CHLOE_COMPARISON_KEY_PASSWORD']
    directory = options.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    for name in ('classes', 'dex'):
        (directory / name).mkdir()
    sdk = options.sdk.resolve()
    build = sdk / 'build-tools' / options.build_tools
    jdk = options.jdk.resolve() / 'bin'
    java = str(jdk / 'java.exe')
    android = sdk / 'platforms' / options.platform / 'android.jar'
    # aapt2's asset provider fails on some Unicode absolute SDK paths on Windows.
    shutil.copy2(android, directory / 'android.jar')
    manifest = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="ai.chloe.match.driver">
<uses-sdk android:minSdkVersion="32" android:targetSdkVersion="35"/>
<application android:label="CHLOE comparison driver" android:debuggable="true"/>
<instrumentation android:name="ai.chloe.match.driver.Driver" android:targetPackage="ai.chloe.match.chloe" android:functionalTest="true"/>
<instrumentation android:name="ai.chloe.match.driver.PocketDriver" android:targetPackage="ai.chloe.match.pocketpal" android:functionalTest="true"/>
</manifest>'''
    (directory / 'AndroidManifest.xml').write_text(manifest, encoding='utf-8')
    sources = list(Path(__file__).resolve().parent.glob('*.java'))
    def run(command):
        subprocess.run(command, cwd=directory, check=True)
    run([str(jdk / 'javac.exe'), '-encoding', 'UTF-8', '-source', '8', '-target', '8', '-classpath', str(android), '-d', 'classes', *map(str, sources)])
    run([java, '-cp', str(build / 'lib/d8.jar'), 'com.android.tools.r8.D8', '--lib', str(android), '--min-api', '32', '--output', 'dex', *map(str, (directory / 'classes').rglob('*.class'))])
    run([str(build / 'aapt2.exe'), 'link', '--manifest', 'AndroidManifest.xml', '-I', 'android.jar', '-o', 'driver-unsigned.apk'])
    with zipfile.ZipFile(directory / 'driver-unsigned.apk', 'a') as archive:
        archive.write(directory / 'dex/classes.dex', 'classes.dex')
    run([java, '-jar', str(build / 'lib/apksigner.jar'), 'sign', '--ks', str(options.keystore.resolve()), '--ks-key-alias', 'comparison', '--ks-pass', 'env:CHLOE_COMPARISON_KEY_PASSWORD', '--key-pass', 'env:CHLOE_COMPARISON_KEY_PASSWORD', '--out', 'driver.apk', 'driver-unsigned.apk'])
    run([java, '-jar', str(build / 'lib/apksigner.jar'), 'verify', 'driver.apk'])
    print(directory / 'driver.apk')


if __name__ == '__main__':
    main()
