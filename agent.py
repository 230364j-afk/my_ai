import json
import os
import subprocess
from pathlib import Path

import requests


# ============================================================
# 설정
# ============================================================

MODEL = "qwen3:8b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE = BASE_DIR / "workspace"

WORKSPACE.mkdir(exist_ok=True)


# ============================================================
# 파일 접근 보호
# ============================================================

def safe_path(relative_path: str) -> Path:
    """
    workspace 밖으로 나가지 못하도록 경로를 제한합니다.
    """

    relative_path = relative_path.replace("\\", "/")

    target = (WORKSPACE / relative_path).resolve()

    if target != WORKSPACE and WORKSPACE not in target.parents:
        raise ValueError("workspace 밖의 파일에는 접근할 수 없습니다.")

    return target


# ============================================================
# Tool 1 : 파일 목록
# ============================================================

def list_files():
    files = []

    for path in WORKSPACE.rglob("*"):
        if path.is_file():
            files.append(str(path.relative_to(WORKSPACE)))

    return files


# ============================================================
# Tool 2 : 파일 읽기
# ============================================================

def read_file(path: str):
    target = safe_path(path)

    if not target.exists():
        return f"파일이 존재하지 않습니다: {path}"

    if not target.is_file():
        return f"파일이 아닙니다: {path}"

    return target.read_text(encoding="utf-8")


# ============================================================
# Tool 3 : 파일 쓰기
# ============================================================

def write_file(path: str, content: str):
    target = safe_path(path)

    target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(content, encoding="utf-8")

    return f"파일 생성/수정 완료: {path}"


# ============================================================
# Tool 4 : 폴더 만들기
# ============================================================

def make_directory(path: str):
    target = safe_path(path)

    target.mkdir(parents=True, exist_ok=True)

    return f"폴더 생성 완료: {path}"


# ============================================================
# Tool 5 : Python 실행
# ============================================================

def run_python(path: str):
    target = safe_path(path)

    if not target.exists():
        return f"파일이 존재하지 않습니다: {path}"

    if target.suffix != ".py":
        return "Python 파일(.py)만 실행할 수 있습니다."

    try:
        result = subprocess.run(
            ["python", str(target)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=20
        )

        return {
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except subprocess.TimeoutExpired:
        return "실행 시간이 20초를 초과했습니다."


# ============================================================
# Tool 실행기
# ============================================================

def execute_tool(action: dict):
    name = action.get("tool")
    args = action.get("args", {})

    try:

        if name == "list_files":
            return list_files()

        elif name == "read_file":
            return read_file(args["path"])

        elif name == "write_file":
            return write_file(
                args["path"],
                args["content"]
            )

        elif name == "make_directory":
            return make_directory(args["path"])

        elif name == "run_python":
            return run_python(args["path"])

        else:
            return f"알 수 없는 도구입니다: {name}"

    except Exception as e:
        return f"도구 실행 오류: {e}"


# ============================================================
# AI에게 주는 규칙
# ============================================================

SYSTEM_PROMPT = r"""
너는 사용자의 개발 작업을 수행하는 로컬 개발 에이전트다.

너의 목표:
- 사용자의 요구를 분석한다.
- 필요한 작업을 스스로 계획한다.
- workspace 내부의 파일을 읽고 작성한다.
- Python 코드를 실행해서 결과를 확인한다.
- 오류가 발생하면 코드를 수정하고 다시 실행한다.

사용 가능한 도구:

1. list_files
2. read_file
3. write_file
4. make_directory
5. run_python

중요한 규칙:

- 한 번에 하나의 작업만 수행한다.
- 도구가 필요하지 않으면 일반 답변을 한다.
- 도구를 사용해야 할 경우 반드시 JSON 하나만 출력한다.
- JSON 형식은 다음과 같다.

{
  "tool": "도구이름",
  "args": {
      "필요한 인자": "값"
  }
}

예:

{
  "tool": "write_file",
  "args": {
      "path": "hello.py",
      "content": "print('hello')"
  }
}

파일을 생성한 뒤 실행해서 오류가 있는지 확인할 수 있다.

workspace 밖의 파일에는 접근하려고 하지 않는다.
"""


# ============================================================
# Ollama 호출
# ============================================================

def ask_ai(messages):

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    return data["message"]["content"]


# ============================================================
# JSON 파싱
# ============================================================

def try_parse_action(text: str):

    text = text.strip()

    try:
        return json.loads(text)

    except json.JSONDecodeError:

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            return None

        try:
            return json.loads(
                text[start:end + 1]
            )
        except json.JSONDecodeError:
            return None


# ============================================================
# Agent
# ============================================================

def run_agent(user_input: str):

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": user_input
        }
    ]

    for step in range(10):

        print(f"\n[AI 작업 {step + 1}/10]")

        result = ask_ai(messages)

        print("\nAI:")
        print(result)

        action = try_parse_action(result)

        # 일반 답변
        if not action or "tool" not in action:
            return result

        print("\n[도구 실행]")
        print(json.dumps(
            action,
            ensure_ascii=False,
            indent=2
        ))

        tool_result = execute_tool(action)

        print("\n[도구 결과]")
        print(tool_result)

        messages.append({
            "role": "assistant",
            "content": result
        })

        messages.append({
            "role": "user",
            "content": (
                "도구 실행 결과:\n"
                + str(tool_result)
                + "\n\n"
                "결과를 분석하고 다음 작업을 계속 진행해."
            )
        })

    return "최대 작업 횟수에 도달했습니다."


# ============================================================
# 프로그램 시작
# ============================================================

def main():

    print("=" * 60)
    print("My Local Development AI")
    print("=" * 60)

    print(f"Workspace: {WORKSPACE}")

    while True:

        try:
            user_input = input("\nYou: ")

        except KeyboardInterrupt:
            print("\n종료합니다.")
            break

        if user_input.lower() in {
            "exit",
            "quit"
        }:
            break

        if not user_input.strip():
            continue

        try:
            run_agent(user_input)

        except Exception as e:
            print("\n오류:")
            print(e)


if __name__ == "__main__":
    main()
