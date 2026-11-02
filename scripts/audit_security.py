import re
import subprocess
import os

PATTERNS = {
    "AWS Access Key ID": r"\bAKIA[0-9A-Z]{16}\b",
    "AWS Secret Access Key": r"(?i)aws_secret_access_key\s*[:=]\s*['\"][A-Za-z0-9/\+=]{40}['\"]",
    "GitHub Personal Access Token": r"\b(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{50,})\b",
    "GitHub OAuth / App Token": r"\b(gho_[a-zA-Z0-9]{36}|ghs_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36})\b",
    "OpenAI API Key": r"\bsk-[a-zA-Z0-9_\-]{20,}\b",
    "Anthropic API Key": r"\bsk-ant-[a-zA-Z0-9_\-]{20,}\b",
    "Google Gemini/Cloud API Key": r"\bAIza[0-9A-Za-z\-_]{35}\b",
    "Private Key Block": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "Slack Token": r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b",
    "Generic Password Assignment": r"(?i)(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{6,}['\"]",
    "Generic Secret / Token Assignment": r"(?i)(?:secret|api_key|apikey|access_token|auth_token)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
    "Bearer Authorization Header": r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{25,}",
    "Basic Auth Embedded in URL": r"https?://[^:\s]+:[^@\s]+@",
    "Hardcoded Private IP / Credential URL": r"https?://(?:root|admin):[^@\s]+@"
}

EXCLUDE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".ico", ".bin"}

def scan_tracked_files():
    print("=" * 70)
    print("1. ESCANEANDO ARCHIVOS RASTREADOS EN EL REPOSITORIO (git ls-files)")
    print("=" * 70)

    res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    files = res.stdout.splitlines()

    total_scanned = 0
    findings = []

    for rel_path in files:
        _, ext = os.path.splitext(rel_path)
        if ext in EXCLUDE_EXTENSIONS:
            continue
        if not os.path.isfile(rel_path):
            continue

        total_scanned += 1
        with open(rel_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, start=1):
                clean_line = line.strip()
                # Omit empty lines or markdown table delimiters
                if not clean_line or clean_line.startswith("| :---"):
                    continue

                for p_name, regex in PATTERNS.items():
                    matches = re.finditer(regex, clean_line)
                    for m in matches:
                        matched_str = m.group(0)
                        # Filter out documentation examples, type definitions, or schema names
                        if "your_api_key" in matched_str.lower() or "example" in matched_str.lower():
                            continue
                        findings.append({
                            "type": p_name,
                            "file": rel_path,
                            "line": line_no,
                            "snippet": clean_line[:120],
                            "match": matched_str
                        })

    print(f"Total de archivos rastreados inspeccionados: {total_scanned}")
    if not findings:
        print(">> RESULTADO: 0 CLAVES O TOKENS DETECTADOS EN ARCHIVOS RASTREADOS.")
    else:
        print(f">> ALERTA: Se encontraron {len(findings)} posibles coincidencias:")
        for f in findings:
            print(f"   [{f['type']}] {f['file']}:{f['line']} -> {f['snippet']}")

    return findings


def scan_untracked_and_ignored():
    print("\n" + "=" * 70)
    print("2. ESCANEANDO ARCHIVOS NO RASTREADOS / IGNORADOS EN EL ESPACIO DE TRABAJO")
    print("=" * 70)

    # Check for sensitive file names like .env, id_rsa, *.pem, credentials.json
    sensitive_file_patterns = [
        re.compile(r"^\.env.*$", re.IGNORECASE),
        re.compile(r"^.*credential.*\.json$", re.IGNORECASE),
        re.compile(r"^.*client_secret.*\.json$", re.IGNORECASE),
        re.compile(r"^.*\.pem$", re.IGNORECASE),
        re.compile(r"^.*\.key$", re.IGNORECASE),
        re.compile(r"^.*id_rsa.*$", re.IGNORECASE),
        re.compile(r"^.*id_ed25519.*$", re.IGNORECASE),
    ]

    suspect_files = []
    for root, dirs, files in os.walk("."):
        # Skip .git directory
        if ".git" in root.split(os.sep):
            continue
        for fname in files:
            for s_regex in sensitive_file_patterns:
                if s_regex.match(fname):
                    suspect_files.append(os.path.join(root, fname))

    if not suspect_files:
        print(">> RESULTADO: No existen archivos sensibles (.env, .pem, credentials.json) en el árbol del proyecto.")
    else:
        print(f">> ALERTA: Se encontraron {len(suspect_files)} archivos con nombres sensibles:")
        for sf in suspect_files:
            print(f"   - {sf}")

    return suspect_files


def scan_git_history():
    print("\n" + "=" * 70)
    print("3. ESCANEANDO HISTORIAL COMPLETO DE COMMITS Y DIFFS (git log -p --all)")
    print("=" * 70)

    res = subprocess.run(["git", "log", "-p", "--all"], capture_output=True, text=True, errors="ignore")
    log_content = res.stdout

    history_findings = []
    current_commit = "HEAD"

    for line in log_content.splitlines():
        if line.startswith("commit "):
            current_commit = line.split()[1][:10]
            continue
        # Only inspect added lines
        if not line.startswith("+"):
            continue
        clean_line = line[1:].strip()
        if not clean_line or clean_line.startswith("| :---"):
            continue

        for p_name, regex in PATTERNS.items():
            matches = re.finditer(regex, clean_line)
            for m in matches:
                matched_str = m.group(0)
                if "your_api_key" in matched_str.lower() or "example" in matched_str.lower():
                    continue
                history_findings.append({
                    "commit": current_commit,
                    "type": p_name,
                    "snippet": clean_line[:120],
                    "match": matched_str
                })

    print(f"Total de líneas de diffs históricos inspeccionadas: {len(log_content.splitlines())}")
    if not history_findings:
        print(">> RESULTADO: 0 CLAVES O TOKENS DETECTADOS EN EL HISTORIAL DE COMMITS.")
    else:
        print(f">> ALERTA: Se encontraron {len(history_findings)} posibles secretos en el historial de commits:")
        for h in history_findings:
            print(f"   [Commit {h['commit']}] [{h['type']}] -> {h['snippet']}")

    return history_findings


def scan_git_config_and_remotes():
    print("\n" + "=" * 70)
    print("4. ESCANEANDO CONFIGURACIÓN LOCAL DE GIT Y REMOTOS")
    print("=" * 70)

    res_remotes = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True)
    remotes = res_remotes.stdout.strip()
    print("Remotos configurados:")
    print(remotes)

    leak_in_remote = False
    for line in remotes.splitlines():
        if re.search(r"https?://[^:\s]+:[^@\s]+@", line) or "ghp_" in line or "github_pat_" in line:
            leak_in_remote = True
            print(f">> ALERTA: Credencial expuesta en la URL del remoto: {line}")

    if not leak_in_remote:
        print(">> RESULTADO: Las URLs de los remotos están limpias y seguras (no contienen tokens incrustados).")


if __name__ == "__main__":
    t_findings = scan_tracked_files()
    u_findings = scan_untracked_and_ignored()
    h_findings = scan_git_history()
    scan_git_config_and_remotes()
