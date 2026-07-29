import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import random
import re
from types import ModuleType


BASE_DIR = Path(__file__).resolve().parent
NOTEBOOK_PATH = BASE_DIR / "MAIN.ipynb"
JSON_OUTPUT_DIR = BASE_DIR / "activities" / "json_outputs"


def ensure_correct_python_environment():
    target_python = Path(os.getenv("WORKSHEET_BACKEND_PYTHON", r"C:\Users\isabe\anaconda3\envs\main\python.exe"))
    if not target_python.exists():
        return

    try:
        current_python = Path(sys.executable).resolve()
        target_python = target_python.resolve()
    except Exception:
        return

    if current_python == target_python:
        return

    print(f"[backend] Relaunching under {target_python}", flush=True)
    import subprocess

    target_env_dir = target_python.parent
    env = os.environ.copy()
    path_entries = [
        str(target_env_dir),
        str(target_env_dir / "Scripts"),
        str(target_env_dir / "Library" / "bin"),
    ]
    existing_path = env.get("PATH", "")
    valid_entries = [entry for entry in path_entries if Path(entry).exists()]
    env["PATH"] = ";".join(valid_entries + ([existing_path] if existing_path else []))
    env["PYTHONUNBUFFERED"] = "1"

    subprocess.run(
        [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(BASE_DIR),
        env=env,
        check=False,
    )
    raise SystemExit(0)


def latest_png_path(folder_path):
    folder = Path(folder_path)
    png_files = sorted(folder.glob("*.png"), key=lambda file_path: file_path.stat().st_mtime if file_path.exists() else 0)
    return str(png_files[-1]) if png_files else None


def load_env_file():
    candidates = [BASE_DIR / "PROMPTFOO" / ".env", BASE_DIR / ".env"]
    for candidate in candidates:
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_openai_api_key():
    load_env_file()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY was not found in PROMPTFOO/.env or the environment")
    return api_key


def call_openai_json(prompt, model="gpt-4o-mini", temperature=0.8):
    import json as _json
    import urllib.request as _request

    api_key = get_openai_api_key()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You return valid raw JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    request = _request.Request(
        os.getenv("OPENAI_CHAT_ENDPOINT", "https://api.openai.com/v1/chat/completions"),
        data=_json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with _request.urlopen(request, timeout=180) as response:
        response_body = _json.loads(response.read().decode("utf-8"))
    content = response_body["choices"][0]["message"]["content"]
    return _json.loads(content)


def save_json_output(folder, filename, payload):
    target_folder = Path(folder)
    target_folder.mkdir(parents=True, exist_ok=True)
    output_path = target_folder / filename
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_path)


def _infer_activity_kind(filename):
    lower_name = filename.lower()
    if "pattern" in lower_name:
        return "pattern"
    if "sequencing" in lower_name:
        return "sequencing"
    if "logic" in lower_name:
        return "logic"
    return "unknown"


def _infer_level(filename):
    lower_name = filename.lower()
    for level_name in ("beginner", "intermediate", "hard"):
        if level_name in lower_name:
            return level_name
    return "unknown"


def install_import_stubs():
    if "dotenv" not in sys.modules:
        dotenv_stub = ModuleType("dotenv")

        def load_dotenv(*args, **kwargs):
            return True

        dotenv_stub.load_dotenv = load_dotenv
        sys.modules["dotenv"] = dotenv_stub

    # Never stub cairosvg. Pattern icons need real SVG->PNG conversion.
    if "cairosvg" in sys.modules and getattr(sys.modules["cairosvg"], "__file__", None) is None:
        sys.modules.pop("cairosvg", None)

    try:
        __import__("cairosvg")
    except Exception as exc:
        raise RuntimeError(
            "cairosvg is required for pattern icons in backend.py. "
            "Install/launch backend in the same environment as the notebook."
        ) from exc


def _clean_notebook_cell(source_text):
    if "pattern_generation_specs = [" in source_text and "generate_openai_payload(" in source_text:
        return ""

    cleaned_lines = []
    for raw_line in source_text.splitlines():
        stripped_line = raw_line.strip()

        if not stripped_line:
            cleaned_lines.append(raw_line)
            continue

        if stripped_line.startswith("load_dotenv("):
            continue

        if stripped_line in {
            "generate_pattern_worksheet()",
            "generate_pattern_intermediate_worksheet()",
            "generate_pattern_hard_worksheet()",
            "generate_beginner_worksheet()",
            "generate_intermediate_worksheet()",
            "generate_hard_worksheet()",
        }:
            continue

        if re.match(r"^test_data_[A-Za-z0-9_]+\s*=\s*_generate_logic_payload_relaxed\(", stripped_line):
            continue

        if re.match(r"^sequencing_[A-Za-z0-9_]+\s*=\s*generate_openai_payload\(", stripped_line):
            continue

        if re.match(r"^pattern_[A-Za-z0-9_]+\s*=\s*generate_openai_payload\(", stripped_line):
            continue

        cleaned_lines.append(raw_line)

    return "\n".join(cleaned_lines)


def load_notebook_namespace():
    if not NOTEBOOK_PATH.exists():
        raise RuntimeError(f"Notebook not found: {NOTEBOOK_PATH}")

    install_import_stubs()
    load_env_file()
    notebook_data = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    namespace = {"__builtins__": __builtins__}

    for cell in notebook_data.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source_text = "".join(cell.get("source", []))
        cleaned_source = _clean_notebook_cell(source_text)
        if cleaned_source.strip():
            exec(compile(cleaned_source, str(NOTEBOOK_PATH), "exec"), namespace)

            if "generate_beginner_spot_diff" in cleaned_source and "def generate_beginner_worksheet()" in cleaned_source:
                namespace["logic_generate_beginner_worksheet"] = namespace["generate_beginner_worksheet"]
                namespace["logic_generate_intermediate_worksheet"] = namespace["generate_intermediate_worksheet"]
                namespace["logic_generate_hard_worksheet"] = namespace["generate_hard_worksheet"]

    return namespace


ensure_correct_python_environment()


def get_prompt_name(activity, difficulty, index):
    if activity == "logic":
        return f"logic_{difficulty}_prompt_{index}"
    return f"{activity}_{difficulty}_prompt_{index}"


def get_payload_name(activity, difficulty, index):
    if activity == "logic":
        return f"test_data_{difficulty}_{index}"
    return f"{activity}_{difficulty}_{index}"


def get_filename(activity, difficulty, index):
    return f"{activity}_{difficulty}_{index}.json"


def get_temperature(activity, difficulty):
    if activity == "sequencing":
        return 0.4 if difficulty != "hard" else 0.35
    if activity == "logic":
        return {"beginner": 0.95, "intermediate": 0.9, "hard": 0.8}[difficulty]
    return {"beginner": 0.6, "intermediate": 0.55, "hard": 0.5}[difficulty]


ALLOWED_PATTERN_SIGNATURES = {
    "beginner": {"ABABA", "AABBA"},
    "intermediate": {"AABAAB", "ABBABB", "ABCABC", "AABBAA"},
    "hard": {"ABACABAC", "ABCABCAB", "AABCAABC", "ABBCABBC"},
}
_BACKEND_PATTERN_DECKS = {
    "beginner": [],
    "intermediate": [],
    "hard": [],
}


def _pattern_full_signature(payload):
    if not isinstance(payload, dict):
        return None

    sequence = payload.get("sequence")
    correct_answer = payload.get("correct_answer")
    if not isinstance(sequence, list) or not sequence:
        return None
    if not isinstance(correct_answer, str) or not correct_answer.strip():
        return None
    if sequence.count("?") != 1:
        return None

    full_sequence = []
    for item in sequence:
        if not isinstance(item, str):
            return None
        token = item.strip()
        if not token:
            return None
        if token == "?":
            token = correct_answer.strip()
        full_sequence.append(token)

    symbol_map = {}
    next_codepoint = ord("A")
    signature = []
    for token in full_sequence:
        if token not in symbol_map:
            symbol_map[token] = chr(next_codepoint)
            next_codepoint += 1
        signature.append(symbol_map[token])

    return "".join(signature)


def _is_allowed_pattern_payload(payload, difficulty):
    signature = _pattern_full_signature(payload)
    if signature is None:
        return False, None
    return signature in ALLOWED_PATTERN_SIGNATURES[difficulty], signature


def _choose_target_pattern_signatures(difficulty, count):
    families = sorted(ALLOWED_PATTERN_SIGNATURES[difficulty])
    deck = _BACKEND_PATTERN_DECKS.get(difficulty)
    if deck is None:
        deck = []
        _BACKEND_PATTERN_DECKS[difficulty] = deck

    rng = random.SystemRandom()
    targets = []

    while len(targets) < count:
        if not deck:
            deck.extend(families)
            rng.shuffle(deck)

        next_family = deck.pop(0)
        # Avoid immediate duplicates inside the same response batch.
        if targets and next_family == targets[-1]:
            deck.append(next_family)
            continue

        targets.append(next_family)

    return targets


def _log_pattern_payload(filename, payload):
    signature = _pattern_full_signature(payload)
    sequence = payload.get("sequence") if isinstance(payload, dict) else None
    print(
        f"[backend] pattern payload {filename}: signature={signature} sequence={sequence}",
        flush=True,
    )


def get_worksheet_name(activity, difficulty):
    if activity == "pattern":
        return {
            "beginner": "generate_pattern_worksheet",
            "intermediate": "generate_pattern_intermediate_worksheet",
            "hard": "generate_pattern_hard_worksheet",
        }[difficulty]
    if activity == "logic":
        return {
            "beginner": "logic_generate_beginner_worksheet",
            "intermediate": "logic_generate_intermediate_worksheet",
            "hard": "logic_generate_hard_worksheet",
        }[difficulty]
    return {
        "beginner": "generate_beginner_worksheet",
        "intermediate": "generate_intermediate_worksheet",
        "hard": "generate_hard_worksheet",
    }[difficulty]


def generate_with_notebook(activity, difficulty, interactive=False, puzzle_count=3):
    notebook_ns = load_notebook_namespace()
    get_openai_api_key()
    notebook_ns["SELECTED_ACTIVITY"] = activity
    notebook_ns["SELECTED_DIFFICULTY"] = difficulty

    # Keep notebook runtime constraints aligned with deterministic validator rules.
    # Beginner patterns must use at least 2 unique items, so exclude the AAAAA target.
    if activity == "pattern":
        notebook_allowed = notebook_ns.get("PATTERN_ALLOWED_SIGNATURES")
        if isinstance(notebook_allowed, dict):
            beginner_allowed = notebook_allowed.get("beginner")
            if isinstance(beginner_allowed, list):
                notebook_allowed["beginner"] = [sig for sig in beginner_allowed if sig != "AAAAA"]
            elif isinstance(beginner_allowed, set):
                beginner_allowed.discard("AAAAA")

        notebook_decks = notebook_ns.get("_PATTERN_FAMILY_DECKS")
        if isinstance(notebook_decks, dict):
            beginner_deck = notebook_decks.get("beginner")
            if isinstance(beginner_deck, list):
                notebook_decks["beginner"] = [sig for sig in beginner_deck if sig != "AAAAA"]

    payloads = []

    if activity == "logic":
        prompt_texts = notebook_ns[f"logic_{difficulty}_prompts"]
        temperatures = {"beginner": 0.95, "intermediate": 0.9, "hard": 0.8}[difficulty]
        generator = notebook_ns["_generate_logic_payload_relaxed"]
        for index, prompt_text in enumerate(prompt_texts, start=1):
            filename = get_filename(activity, difficulty, index)
            payload = generator(f"{prompt_text} {difficulty}", filename, temperature=temperatures)
            notebook_ns[get_payload_name(activity, difficulty, len(payloads) + 1)] = payload
            payloads.append(payload)
    else:
        generator = notebook_ns["generate_openai_payload"]
        if not isinstance(puzzle_count, int):
            puzzle_count = 3
        puzzle_count = max(1, min(3, puzzle_count))
        prompt_names = [get_prompt_name(activity, difficulty, index) for index in range(1, puzzle_count + 1)]
        filename_names = [get_filename(activity, difficulty, index) for index in range(1, puzzle_count + 1)]
        target_signatures = []
        if activity == "pattern":
            target_signatures = _choose_target_pattern_signatures(difficulty, len(prompt_names))
        level_history = None
        batch_signatures = set()

        if activity == "pattern" and all(
            key in notebook_ns
            for key in ("_load_existing_pattern_history", "_augment_pattern_prompt_for_regeneration", "_pattern_items_from_sequence", "_pattern_signature")
        ):
            history = notebook_ns["_load_existing_pattern_history"]()
            level_history = history.setdefault(difficulty, {"items": set(), "signatures": set()})

        for sample_index, (prompt_name, filename, temperature) in enumerate(
            zip(prompt_names, filename_names, [get_temperature(activity, difficulty)] * 3),
            start=1,
        ):
            prompt_text = notebook_ns[prompt_name]
            target_signature = None
            if activity == "pattern":
                target_signature = target_signatures[sample_index - 1]

            if activity == "pattern" and level_history is not None:
                prompt_text = notebook_ns["_augment_pattern_prompt_for_regeneration"](
                    prompt_name,
                    banned_items=level_history.get("items", set()),
                    banned_signatures=level_history.get("signatures", set()) | batch_signatures,
                )

            if activity == "pattern" and target_signature is not None:
                prompt_text = (
                    f"{prompt_text}\n\n"
                    f"STRUCTURE TARGET (must follow exactly for this output): {target_signature}. "
                    "Use exactly that letter pattern with 1-word items from one allowed category."
                )

            payload = None
            if activity == "pattern":
                allowed_payload = False
                last_signature = None
                local_prompt = prompt_text
                for attempt in range(1, 7):
                    payload = generator(local_prompt, filename, temperature=temperature)
                    allowed_payload, last_signature = _is_allowed_pattern_payload(payload, difficulty)
                    if allowed_payload and (target_signature is None or last_signature == target_signature):
                        break
                    if allowed_payload and target_signature is not None and last_signature != target_signature:
                        allowed_payload = False
                    local_prompt = (
                        f"{prompt_text}\n\n"
                        f"Previous attempt produced invalid structure: {last_signature or 'unknown'}. "
                        f"Allowed structures for {difficulty}: {', '.join(sorted(ALLOWED_PATTERN_SIGNATURES[difficulty]))}. "
                        f"Required structure for this output: {target_signature}. "
                        "Return a different valid sequence."
                    )

                if not allowed_payload:
                    raise RuntimeError(
                        f"Pattern payload for {filename} failed allowed-structure checks after retries. "
                        f"Last structure: {last_signature or 'unknown'}"
                    )
                batch_signatures.add(last_signature)
            else:
                payload = generator(prompt_text, filename, temperature=temperature)

            notebook_ns[get_payload_name(activity, difficulty, len(payloads) + 1)] = payload
            payloads.append(payload)

            if activity == "pattern":
                _log_pattern_payload(filename, payload)
                if level_history is not None:
                    sequence = payload.get("sequence") if isinstance(payload, dict) else None
                    level_history["items"].update(notebook_ns["_pattern_items_from_sequence"](sequence))
                    sequence_signature = notebook_ns["_pattern_signature"](sequence)
                    if sequence_signature:
                        level_history["signatures"].add(sequence_signature)
                if interactive and "generate_pattern_image" in notebook_ns:
                    image_path = notebook_ns["generate_pattern_image"](payload)
                    if image_path and isinstance(payload, dict):
                        payload["__image_path"] = image_path

            elif activity == "sequencing":
                if interactive and "generate_size_ordering_from_llm" in notebook_ns:
                    image_path = notebook_ns["generate_size_ordering_from_llm"](payload)
                    if image_path and isinstance(payload, dict):
                        payload["__image_path"] = image_path

    worksheet_function_name = get_worksheet_name(activity, difficulty)
    worksheet_path = None
    if not interactive:
        worksheet_function = notebook_ns[worksheet_function_name]
        worksheet_path = worksheet_function()

    if activity == "pattern":
        png_folder = BASE_DIR / "activities" / "pattern"
    elif activity == "logic":
        png_folder = BASE_DIR / "activities" / "logic problem solving"
    else:
        png_folder = BASE_DIR / "activities" / "sequencing"

    return {
        "activity": activity,
        "difficulty": difficulty,
        "interactive": bool(interactive),
        "payloads": payloads,
        "worksheet_function": worksheet_function_name,
        "worksheet_path": worksheet_path,
        "png_path": latest_png_path(png_folder),
    }


class WorksheetHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, body):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/generate":
            self._send_json(404, {"error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(content_length)
            request_data = json.loads(request_body.decode("utf-8"))

            activity = str(request_data.get("activity", "")).strip().lower()
            difficulty = str(request_data.get("difficulty", "")).strip().lower()
            interactive = bool(request_data.get("interactive", False))
            puzzle_count = request_data.get("puzzle_count", 3)
            if not isinstance(puzzle_count, int):
                puzzle_count = 3

            if activity not in {"pattern", "logic", "sequencing"}:
                self._send_json(400, {"error": "Invalid activity"})
                return
            if difficulty not in {"beginner", "intermediate", "hard"}:
                self._send_json(400, {"error": "Invalid difficulty"})
                return

            print(f"[backend] POST /generate activity={activity} difficulty={difficulty}", flush=True)
            result = generate_with_notebook(activity, difficulty, interactive=interactive, puzzle_count=puzzle_count)
            self._send_json(200, result)
        except Exception as exc:
            print(f"[backend] ERROR: {exc}", flush=True)
            traceback.print_exc()
            self._send_json(500, {"error": str(exc)})


def main():
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"  # must bind to 0.0.0.0 for Render (not 127.0.0.1)
    server = ThreadingHTTPServer((host, port), WorksheetHandler)
    print(f"Backend running at http://{host}:{port}")
    print("GET /health and POST /generate")
    server.serve_forever()


if __name__ == "__main__":
    main()