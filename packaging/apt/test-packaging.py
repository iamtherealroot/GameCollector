"""Real DEB/APT-signature checks; deployment hooks use disposable Docker stubs."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent

def run(args, **kwargs):
    r=subprocess.run(list(map(str,args)),text=True,capture_output=True,**kwargs)
    if r.returncode: raise RuntimeError(f"{args}: {r.stderr}")
    return r.stdout

with tempfile.TemporaryDirectory(prefix="bibo-apt-check-") as folder:
    base=Path(folder);base.chmod(0o755)
    release=base/"release";(release/"app").mkdir(parents=True)
    (release/"app/app.py").write_text('APP_VERSION = "5.1.1"\n')
    (release/"docker-compose.yml").write_text("services: {}\n")
    (release/"install.sh").write_text("#!/bin/bash\nexit 0\n")
    (release/".env").write_text("DO_NOT_PACKAGE=private-fixture\n")
    package_dir=base/"packages"
    run(["bash",TOOLS/"build-deb.sh",release,package_dir])
    package=package_dir/"bibo_5.1.1-1_all.deb"
    assert run(["dpkg-deb","-f",package,"Version"]).strip()=="5.1.1-1"
    assert ".env" not in run(["dpkg-deb","-c",package])
    controls=base/"controls";payload_root=base/"unpacked"
    run(["dpkg-deb","--control",package,controls])
    run(["dpkg-deb","--extract",package,payload_root])
    payload=payload_root/"usr/share/bibo/release"
    runtime=base/"runtime";runtime.mkdir()
    (runtime/".env").write_text("MUST_REMAIN\n")
    (runtime/"docker-compose.yml").write_text("services: {}\n")
    config=base/"bibo-apt.conf";config.write_text("BIBO_INSTALL_DIR="+str(runtime)+"\n")
    state=base/"state";state.mkdir()
    bin_dir=base/"bin";bin_dir.mkdir()
    (bin_dir/"docker").write_text("""#!/bin/bash
case "$*" in
  "compose version") echo "Docker Compose v2";;
  "compose exec -T web python -c "*) cat "$BIBO_TEST_CURRENT";;
  "compose stop web scheduler") echo stopped > "$BIBO_TEST_STOP";;
  *) exit 9;;
esac
""")
    (bin_dir/"docker").chmod(0o755)
    current=base/"current";current.write_text("5.1.0\n")
    stopped=base/"stopped"
    env={**os.environ,"PATH":str(bin_dir)+os.pathsep+os.environ["PATH"],
         "BIBO_TEST_CURRENT":str(current),"BIBO_TEST_STOP":str(stopped)}
    for name in ["postinst","prerm","postrm"]:
        text=(controls/name).read_text().replace("/opt/gamecollector",str(runtime)).replace("/etc/bibo-apt.conf",str(config)).replace("/usr/share/bibo/release",str(payload)).replace("/var/lib/bibo-apt",str(state))
        (base/name).write_text(text)
    # A failed update never marks first adoption as successful.
    (payload/"install.sh").write_text("#!/bin/bash\nexit 17\n")
    failed=subprocess.run(["bash",str(base/"postinst"),"configure"],env=env,capture_output=True)
    assert failed.returncode==17 and not (state/"managed-version").exists()
    run(["bash",base/"prerm","remove"],env=env)
    assert not stopped.exists(), "Failed first adoption must not stop the original app"
    (payload/"install.sh").write_text('#!/bin/bash\nprintf "5.1.1\\n" > "$BIBO_TEST_CURRENT"\n')
    run(["bash",base/"postinst","configure"],env=env)
    assert (state/"managed-version").read_text().strip()=="5.1.1"
    # Same-version adoption skips the installer; downgrade does not deploy.
    (payload/"install.sh").write_text("#!/bin/bash\nexit 19\n")
    run(["bash",base/"postinst","configure"],env=env)
    current.write_text("5.1.2\n")
    downgrade=subprocess.run(["bash",str(base/"postinst"),"configure"],env=env,capture_output=True)
    assert downgrade.returncode!=0 and current.read_text().strip()=="5.1.2"
    run(["bash",base/"prerm","upgrade"],env=env);assert not stopped.exists()
    run(["bash",base/"prerm","remove"],env=env);assert stopped.exists()
    run(["bash",base/"postrm","purge"],env=env)
    assert (runtime/".env").read_text()=="MUST_REMAIN\n" and runtime.exists()
    print("OK: DEB payload, update hooks, failed adoption/retry, downgrade guard, data retention", flush=True)
    if os.environ.get("BIBO_APT_HOOK_TEST_ONLY") == "1":
        raise SystemExit(0)
    # APT accepts the scoped signature and advertises the packaged version.
    key_home=base/"gpg";key_home.mkdir(mode=0o700)
    run(["gpg","--homedir",key_home,"--batch","--pinentry-mode","loopback","--passphrase","","--quick-generate-key","Bibo disposable packaging test","rsa2048","sign","0"])
    fpr=next(line.split(":")[9] for line in run(["gpg","--homedir",key_home,"--batch","--with-colons","--list-secret-keys"]).splitlines() if line.startswith("fpr:"))
    site=base/"site"
    run(["bash",TOOLS/"build-repository.sh",package,site,key_home,fpr])
    assert fpr in run(["gpg","--batch","--with-colons","--show-keys",site/"bibo-archive-key.asc"])
    keyring=base/"keyring.gpg"
    run(["gpg","--batch","--yes","--dearmor","--output",keyring,site/"bibo-archive-key.asc"])
    keyring.chmod(0o644)
    source=base/"bibo.list";source.write_text(f"deb [signed-by={keyring}] file:{site} stable main\n")
    (base/"status").write_text("")
    for name in ["lists/partial","cache/archives/partial","logs"]:(base/name).mkdir(parents=True,exist_ok=True)
    options=["-o","Dir::Etc::sourcelist="+str(source),"-o","Dir::Etc::sourceparts=-",
             "-o","Dir::Etc::main=-","-o","Dir::Etc::parts=-",
             "-o","Dir::State::lists="+str(base/"lists"),"-o","Dir::State::status="+str(base/"status"),
             "-o","Dir::Cache="+str(base/"cache"),"-o","Dir::Log="+str(base/"logs"),
             "-o","APT::Sandbox::User=root","-o","APT::Update::Error-Mode=any"]
    run(["apt-get",*options,"update"])
    policy=run(["apt-cache",*options,"policy","bibo"])
    assert "Candidate: 5.1.1-1" in policy and "100 " in policy,policy
    # Modifying signed metadata must fail, including with a previous good cache.
    metadata=site/"dists/stable/InRelease"
    metadata.write_text(metadata.read_text().replace("Origin: Bibo","Origin: Changed"))
    invalid=subprocess.run(["apt-get",*options,"update"],text=True,capture_output=True)
    assert invalid.returncode!=0,invalid.stdout+invalid.stderr
    assert "BADSIG" in invalid.stderr or "invalid" in invalid.stderr.lower(),invalid.stderr
print("OK: real DEB, no .env, failed adoption/retry, idempotence, downgrade guard, remove/purge data retention, scoped APT signature and tamper rejection")
