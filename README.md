# 🧠 LangGraph Persistent Memory Lab

Bài lab: xây chatbot có **trí nhớ persistent nhiều session** bằng LangChain + LangGraph,
theo pattern **AGENTS.md / MEMORY.md** (index ngắn + file chi tiết theo chủ đề).

**Không dùng database.** Toàn bộ trạng thái bền vững là **file Markdown** trong `data/`:
đọc được bằng mắt, sửa tay được, và agent tự quản lý.

Mục tiêu của bài học:

1. Biết **trí nhớ trong session** (lịch sử hội thoại) và **trí nhớ xuyên session** (quy ước).
2. Biết áp dụng **memory lifecycle**: ghi, đọc, sửa, thay thế, quên — thay vì chỉ append.
3. Biết giải quyết **memory sai / lỗi thời** mà không xoá lịch sử.
4. Biết **progressive disclosure**: index luôn nạp, chi tiết nạp khi cần → tránh context bloat.
5. Biết **prompt caching** không bị phá vỡ bởi dynamic prompt.

---

## 1. Kiến trúc bộ nhớ

| Tầng | Lưu ở đâu | Sống qua restart? | Phạm vi | Bật/tắt |
|---|---|---|---|---|
| **Tầng 1 — Trí nhớ trong session** | `data/sessions/<id>.md` | ✅ | 1 session = 1 hội thoại | luôn bật |
| **Tầng 2 — Trí nhớ dài hạn** | `data/memory/<user>/MEMORY.md` + `<topic>.md` | ✅ | xuyên mọi session của 1 user | `MEMORY_LONG_TERM=1` |

```
        user ──► ┌──────────────────────────┐
                 │  agent (create_agent)    │
                 └───────────┬──────────────┘
      dynamic_prompt nạp     │  tools: remember / recall / update / supersede / forget
      ┌──────────────────────┴───────────────────────┐
      ▼                                              ▼
┌──────────────────┐                     ┌────────────────────────────┐
│ AGENTS.md        │  luôn nạp           │ MEMORY.md  (index ngắn)    │ luôn nạp
│ quy ước project │                     │  └─ auth.md                │ nạp khi
└──────────────────┘                     │     preferences.md         │ recall()
                                         │     conventions.md         │
                                         └────────────────────────────┘
┌────────────────────────────┐
│ data/sessions/<id>.md       │  lịch sử hội thoại (đọc/sửa tay được)
└────────────────────────────┘
```

Luồng 1 lượt chat:

```
1. đọc data/sessions/<id>.md            -> lịch sử session
2. đọc data/memory/<user>/MEMORY.md     -> index (ngắn)
3. nạp AGENTS.md + index vào system prompt (dynamic_prompt)
4. agent trả lời; nếu cần chi tiết -> gọi recall(topic) -> nạp <topic>.md
5. ghi lại data/sessions/<id>.md         -> lịch sử mới
```

Hai khái niệm cốt lõi:

- **`thread_id`** = định danh 1 session; mọi session dùng chung 1 agent, chỉ khác `thread_id`.
- **store** (namespace → key → value) = nơi lưu dữ liệu dài hạn, không gắn với thread
  → dùng chung cho mọi session của user.

---

## 2. Pattern AGENTS.md / MEMORY.md (theo case study)

| File | Vai trò |
|---|---|
| `AGENTS.md` (project root) | Quy ước project — luôn nạp vào context |
| `data/memory/<user>/MEMORY.md` | **Index ngắn** — luôn nạp vào context |
| `data/memory/<user>/<topic>.md` | Chi tiết theo chủ đề — chỉ nạp khi agent gọi `recall(topic)` |
| `data/sessions/<id>.md` | Lịch sử hội thoại (đọc/sửa tay được) |

Index luôn được nạp, chi tiết chỉ nạp khi cần → không nhồi tất cả memory mỗi lượt.

### Vòng đời một mục memory

| Hành động | Tool | Kết quả |
|---|---|---|
| Ghi | `remember(topic, content, supersedes?)` | model đề xuất mục đáng nhớ; harness kiểm tra nội dung/topic/key rồi ghi. Thay thế phải chỉ rõ key cũ |
| Đọc | `recall(topic?)` | nạp chi tiết khi thật cần |
| Sửa | `update(key, content)` | sửa nội dung, giữ nguyên `created_at` |
| Thay thế | `supersede(key, content)` | mục cũ → `status: superseded` + `superseded_by` + `superseded_at` (giữ nguồn, thời điểm) |
| Quên | `forget(key)` | xoá hẳn mục sai / lỗi thời |

> **Model đề xuất, harness kiểm tra:** agent nhận diện quyết định bền vững theo
> ngữ nghĩa, kể cả khi không có từ "lưu/nhớ". Agent đối chiếu index/recall và chỉ
> rõ key cần thay thế. Tool kiểm tra topic, nội dung không rỗng, key thuộc user và
> còn active; không tự thay thế dựa trên từ khóa. Đây không phải bộ đánh giá ngữ
> nghĩa độc lập: chất lượng chọn memory vẫn phụ thuộc model. API `MemoryManager`
> gọi trực tiếp còn giữ heuristic cũ cho các test/lab so sánh, không dùng trong
> đường ghi memory của tool dành cho agent.
>
> Mỗi mục ghi ra đều có `source` = session đã sinh ra nó, và `created_at` / `updated_at`.

### Xử lý memory lỗi thời (ví dụ trong slide)

```
Session 1: "Authentication sử dụng JWT."
Session 2: "Chuyển sang session cookie."
```

→ Agent gọi `supersede(key_cũ, "Authentication sử dụng session cookie")`. Kết quả trong `auth.md`:

```markdown
## fact-898a3db0
- content: Authentication sử dụng JWT
- source: session-1
- status: superseded
- superseded_by: fact-11fa9a81
- superseded_at: 2026-10-22T03:31:38+00:00

## fact-11fa9a81
- content: Authentication sử dụng session cookie
- source: session-2
- status: active
```

Mục cũ **không bị xoá** (vẫn truy vết được), còn `MEMORY.md` chỉ liệt kê quy ước hiện hành.

### Prompt caching: `dynamic_prompt` có làm hỏng cache không?

Cơ chế của mọi provider (Anthropic / OpenAI / Gemini) là **prefix cache**:
> Chỉ phần token **trước** điểm khác biệt đầu tiên được giữ cache; **mọi thứ sau đó phải xử lý lại**.

Nên "ghi memory" **không** phải là "miss toàn bộ" — nó chỉ phá cache từ vị trí thay đổi trở đi.
Vị trí thay đổi phụ thuộc chỗ đặt index memory, và lab hỗ trợ 2 chế độ
(`MEMORY_PLACEMENT` trong `.env`):

| Chế độ | Index memory nằm ở | Khi memory đổi thì xử lý lại |
|---|---|---|
| `system` (mặc định) | cuối **system prompt** | index + **toàn bộ hội thoại** phía sau |
| `end` | cuối **hội thoại** (message `system` cuối cùng) | chỉ digest + lượt chat mới |

→ Muốn **giữ cache cho cả lịch sử hội thoại** thì đặt `MEMORY_PLACEMENT=end`:
system prompt + toàn bộ lịch sử nằm trong prefix ổn định, chỉ phần digest ở đuôi bị tính lại
khi memory đổi (thường là rất hiếm).

Ba điều kiện để giữ cache hit (đã có test tương ứng):

1. **System prompt giống hệt nhau giữa các lượt** → không có timestamp/random trong prompt
   (`test_context_is_byte_identical_between_turns`).
2. **Phần biến động nằm CUỐI** → index ở cuối system prompt, hoặc ở cuối hội thoại nếu `end`
   (`test_volatile_index_is_at_the_end_of_prompt`, `test_placement_end_puts_digest_after_history`).
3. **Index render deterministic** → topic sort, mục giữ thứ tự trong file.

Lưu ý thực tế:

- Prompt caching tiết kiệm **compute**, không phải băng thông — client vẫn gửi toàn bộ prompt.
- Phải đạt **ngưỡng token tối thiểu** mới được cache (thường ~1024–2048 token tùy model/provider);
  nếu `AGENTS.md` quá ngắn thì phần ổn định không đủ dài để cache.
- Cache có TTL (Anthropic ~5 phút, OpenAI/Gemini ~1–2 phút, được refresh khi hit).
- Với Anthropic nên đặt thêm `cache_control={"type": "ephemeral"}` ở cuối phần ổn định
  để chốt breakpoint rõ ràng.

---

## 3. Cấu trúc thư mục

```
memory_agent/
├── AGENTS.md                 # quy ước project (luôn nạp vào context)
├── pyproject.toml            # dependency + cấu hình pytest
├── .env.example              # OPENAI_API_KEY, MODEL_NAME, ...
├── src/memory_agent/
│   ├── config.py             # đọc .env, bật/tắt từng tầng bộ nhớ
│   ├── paths.py              # đường dẫn data/ (resolve theo vị trí file)
│   ├── prompts.py            # system prompt + phần context inject
│   ├── graph.py              # dựng agent: model + middleware + memory
│   ├── memory_tools.py       # tool remember/recall/update/supersede/forget
│   ├── sessions.py           # liệt kê / đặt tên / xoá session
│   ├── runtime.py            # runtime dùng chung cho UI + CLI
│   ├── memory/
│   │   ├── store.py          # MarkdownMemoryStore — index + file chi tiết
│   │   ├── lifecycle.py      # MemoryManager — vòng đời & xung đột
│   │   └── history.py        # lịch sử session (ghi/đọc file Markdown)
│   └── ui/
│       ├── app.py            # FastAPI: API + trang chat
│       └── index.html        # giao diện chat (sidebar session + panel memory/context)
├── scripts/demo_cli.py       # demo bằng terminal
├── tests/                    # pytest, chạy được không cần API key
└── data/                     # sinh ra khi chạy (gitignored)
    ├── memory/<user_id>/MEMORY.md + <topic>.md
    └── sessions/<thread_id>.md
```

Nguyên tắc tổ chức: **mỗi module một trách nhiệm** — đổi nơi lưu memory chỉ cần sửa
`memory/`, không đụng tới agent hay UI.

---

## 4. Cài đặt

Yêu cầu: Python 3.11+, [uv](https://docs.astral.sh/uv/).

```bash
cd memory_agent
uv sync                                   # tạo .venv và cài dependency
cp .env.example .env                     # Windows: copy .env.example .env
```

Hoặc dùng `pip` với Python >=3.11, tại thư mục `memory_agent`:

```bash
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
```

`requirements.txt` cố định phiên bản các thư viện trực tiếp và công cụ kiểm thử
theo môi trường SE373 đã kiểm chứng; các phụ thuộc gián tiếp do pip giải quyết.
Sau đó chạy web bằng `python -m uvicorn memory_agent.ui.app:app --host 127.0.0.1 --port 8000`
và kiểm thử bằng `python -m pytest -q`. Router và `.env` vẫn cần cấu hình riêng.

Điền `.env`:

```dotenv
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4o-mini
OPENAI_BASE_URL=                         # bỏ trống nếu dùng OpenAI mặc định
```

Tuỳ chọn (để thử từng tầng):

```dotenv
MEMORY_LONG_TERM=1            # bật memory dài hạn (tool + index)
MEMORY_PLACEMENT=end           # đặt index memory ở cuối hội thoại (giữ prompt cache)
USER_ID=default-user          # mỗi user một thư mục memory riêng
```

## 5. Chạy

### Giao diện web (FastAPI)

```bash
uv run uvicorn memory_agent.ui.app:app --port 8000
```

Mở http://localhost:8000 — sidebar trái là danh sách session (bấm để chuyển, 🗑 để xoá).
Panel **🧠 Memory** có 3 tab: `Index` (MEMORY.md), `Chi tiết` (từng mục + trạng thái),
`Context` (in ra đúng phần context đang inject vào model).

### Chạy với 9Router global và Miniconda SE373 (Windows)

9Router được cài bằng Node/npm toàn cục, chạy độc lập với Conda. Dự án gọi
9Router qua HTTP từ Python của `SE373`:

```text
Memory Agent (Python SE373) -> http://127.0.0.1:20128/v1 -> OpenCode Free
```

Trong `.env`, dùng API key riêng do dashboard 9Router tạo (không dùng key upstream):

```dotenv
OPENAI_BASE_URL=http://127.0.0.1:20128/v1
OPENAI_API_KEY=<API key trong dashboard 9Router>
MODEL_NAME=oc/glm-5.3-flash-free
```

Model này đã trả `OK` qua 9Router khi kiểm tra ngày 22/10/2026. Danh sách model
miễn phí và khả năng phục vụ có thể thay đổi. Không cần đăng nhập OpenCode Free.

Trong Miniconda Prompt, từ thư mục `BTVN7` hoặc `memory_agent`, khởi động cả hai
dịch vụ chạy nền bằng một lệnh (không cần kích hoạt Conda thủ công):

```bat
run_web
```

Nếu dùng PowerShell, nhập `.\run_web.cmd`.
Launcher dùng Python của môi trường `SE373`. 9Router được lấy từ npm global
(prefix npm/PATH), có in đường dẫn CLI và phiên bản đã cài. Không tự dùng/cài bản
local cũ trong `data/local-router`. Nếu chưa có global, chạy
`npm i -g 9router@latest --prefer-online`. `-RouterCliPath` là override tường minh.
Trước khi dùng lại router trên cổng 20128, launcher kiểm tra đường dẫn tiến trình;
router từ bản local/ứng dụng khác sẽ báo lỗi thay vì âm thầm dùng lại.

Kiểm tra an toàn bằng `run_web -CheckRouterOnly`: chỉ đọc đường dẫn/phiên bản và
trạng thái router, không khởi động/dừng dịch vụ, không thay dữ liệu phiên. Sau khi
update npm khi router đang chạy, dùng `stop_web` rồi `run_web` khi sẵn sàng để
nạp code mới; chỉ cài npm không tự thay code đã nạp trong tiến trình đang chạy.
Có thể đổi cổng bằng `run_web -AppPort 8001`.

Để dừng cả web và 9Router (gồm tiến trình tray), chạy `stop_web` trong Miniconda
Prompt hoặc `.\stop_web.cmd` trong PowerShell, từ `BTVN7` hoặc `memory_agent`.
Lệnh chỉ dừng tiến trình, giữ nguyên memory/lịch sử/checkpoint của A và B cùng
các file dữ liệu. Chạy lại khi đã dừng cũng được. Nếu dùng cổng web khác, truyền
cùng cổng: `stop_web -AppPort 8001`. Có thể xem trước bằng `stop_web -WhatIf`.
Script kiểm tra command line trước khi dừng; nếu cổng thuộc ứng dụng khác sẽ báo
lỗi và giữ ứng dụng đó. Dùng `run_web` để khởi động lại.

Trên giao diện có hai nút để thử nghiệm nhanh:

- **Xóa trí nhớ**: có xác nhận, chỉ xóa memory dài hạn của user hiện tại (cả mục
  active và superseded), rồi mở session mới. Lịch sử và trace cũ vẫn được giữ để
  đối chiếu; snapshot cũ không phải memory hiện hành. Đây là dọn dữ liệu thử,
  không phải cơ chế sửa rò rỉ RAM.
- **Restart web**: khởi động lại tiến trình Python/Uvicorn thật, nạp lại `.env`
  và dữ liệu từ file; giữ nguyên 9Router, memory, lịch sử và trace. Giao diện đợi
  kết nối lại, hiện PID trước/sau và mở session mới cho bước kiểm tra tiếp theo.
  Nếu quá 60 giây chưa kết nối lại, chạy `run_web` và xem
  `data/service-logs/restart-helper.log`.

Hoặc từ thư mục `memory_agent`, chạy trực tiếp script PowerShell:

```powershell
.\scripts\start_local.ps1
```

Script dùng Node global và Python tại `%USERPROFILE%\miniconda3\envs\SE373`,
chỉ bind localhost. Dashboard: http://127.0.0.1:20128/dashboard; ứng dụng chat:
http://127.0.0.1:8000. Log nằm trong `data/service-logs/` đã gitignore.
Không tự thiết lập chạy cùng Windows. Thoát 9Router qua biểu tượng system tray.

Để dùng CLI sau khi router đã chạy:

```powershell
conda activate SE373
python scripts/demo_cli.py chat --thread demo-router "Xin chào"
```

`SE373` hiện dùng Python 3.10.21; test từ source đã chạy được, nhưng metadata
package yêu cầu >=3.11 nên `pip install -e .` vẫn đòi Python >=3.11.

### Demo CLI

```bash
uv run python scripts/demo_cli.py chat --thread s1 "Dự án này dùng JWT để đăng nhập"
uv run python scripts/demo_cli.py chat --thread s2 "Dự án này dùng gì để đăng nhập?"   # session mới, vẫn nhớ
uv run python scripts/demo_cli.py chat --thread s1 "Chuyển sang session cookie nhé"      # quy ước đổi
uv run python scripts/demo_cli.py memory      # xem index + chi tiết memory
uv run python scripts/demo_cli.py context    # in phần context sẽ inject vào model
uv run python scripts/demo_cli.py threads     # xem các session đã lưu
uv run python scripts/demo_cli.py forget --key fact-xxxx   # quên 1 mục
uv run python scripts/demo_cli.py reset       # xoá toàn bộ session (memory giữ nguyên)
uv run python scripts/demo_cli.py wipe        # xoá cả session lẫn memory
```

> Muốn thấy "persistent" rõ ràng: đóng terminal, mở lại, gọi `memory` — dữ liệu vẫn còn
> vì nằm trong `data/`.

### Test (không cần API key)

```bash
uv run pytest
```

Test dùng `MarkdownMemoryStore` thật + fake chat model, nên **chạy offline được**:
kiểm chứng memory xuyên session, lifecycle (sửa/thay thế/quên), xung đột,
lịch sử session nạp lại được, và phần context inject (kể cả tính cache-friendly).

---

## 6. Challenge A: persistent memory (bài tập lớp, timebox 30 phút)

**Mục tiêu:** agent nhớ được quy ước dự án qua nhiều session, và cập nhật khi quy ước thay đổi.

**Chứng minh 1 — session mới vẫn dùng đúng quy ước đã thống nhất**

```bash
uv run python scripts/demo_cli.py chat --thread s1 "Dự án này dùng JWT để đăng nhập"
uv run python scripts/demo_cli.py chat --thread s2 "Dự án này dùng gì để đăng nhập?"
```

**Chứng minh 2 — quy ước đổi thì session sau dùng quy ước mới**

```bash
uv run python scripts/demo_cli.py chat --thread s1 "Chuyển sang session cookie nhé"
uv run python scripts/demo_cli.py chat --thread s2 "Dự án này dùng gì để đăng nhập?"
```

**Kiểm chứng — in ra phần memory đã được inject vào context**

```bash
uv run python scripts/demo_cli.py context
```

### Gợi ý (theo slide)

- **Lưu ở đâu:** Markdown (đọc/sửa tay được), JSON hay SQLite đều đủ — ở đây chọn Markdown, không cần DB.
- **Ai ghi:** agent tự gọi tool (`remember`) hay harness tự trích từ hội thoại?
  → Bài này dùng **agent tự gọi tool** (xem `memory_tools.py`); có thể so sánh với cách trích tự động.
- **Khi nào nạp:** memory vào context lúc mở session hay khi cần mới tìm?
  → **Progressive disclosure**: index nạp lúc mở session, chi tiết nạp khi `recall`.
- **Khi quy ước đổi:** `supersede` thay vì append (xem mục 2).

### Bài tập Challenge B — Context Management

Trang B hỗ trợ **hai chế độ compact**, chọn cạnh nút Compact:

- **Structured compaction** (lựa chọn mặc định trên giao diện): tạo checkpoint có
  goal, current_state, constraints, findings, failed_attempts, files, next_action,
  open_questions. Giữ user/system/developer messages và kế hoạch AI ngắn gần nhất;
  thay output AI/tool dài bằng checkpoint. Provider gọi model trong `.env`, cộng
  usage cả lượt compact thành công hoặc lượt đã gọi nhưng thất bại.
- **Truncation**: giữ N lượt gần nhất (mặc định 2) và prefix system/developer;
  bỏ nguyên lượt cũ, không tách cặp tool call/result. Luôn 0 API, không tạo summary.
  Dùng làm đối chứng vì ràng buộc và bằng chứng ở lượt cũ có thể mất.

Mở **http://127.0.0.1:8000/challenge-b** → chọn Offline hoặc Provider → nạp phiên
mẫu → chọn chế độ → Compact → hỏi bước tiếp theo, ràng buộc và cách đã thử.
Offline structured chỉ trích xuất theo mẫu, không gọi LLM và không chứng minh độ
đúng của summary bằng model. Có thể mở checkpoint trên timeline. Ước lượng context
và usage provider được hiển thị riêng. Ngưỡng mặc định 8.000 chỉ là ngưỡng demo.

Đổi chế độ chỉ chọn cách cho lần compact tiếp theo, không tự chạy và không phục hồi
thông tin đã cắt. Nạp phiên mẫu riêng cho từng chế độ để so sánh cùng đầu vào.
Archive không tự gửi lại model. Structured chỉ cập nhật nếu JSON/schema hợp lệ và
working context nhỏ hơn; các điều kiện này chưa bảo đảm giữ đúng ngữ nghĩa.

B2 dùng cùng bộ **10.000 dòng log giả / 4 file** cho cả hai phương pháp.
Đáp án mới: refresh_timeout 3.000, db_connection 1.800, invalid_token 600.
`run_code` đọc/lọc/đếm log trong runtime, trả findings có bằng chứng;
raw baseline chạy ở chat riêng. Offline đếm bằng code, Provider dùng model `.env`.

**Reset tất cả B** xóa memory B và mở chat mới; **Reset context** chỉ bỏ active
context phiên đang mở. Giữ archive cũ, không tác động namespace Challenge A.
API/CLI chung `/api/compact` và `demo_cli.py compact` giữ hành vi cũ.

Xem [hướng dẫn hai chế độ](CHALLENGE_B_TRUNCATION_GUIDE.md) và
[phần mô tả dùng cho báo cáo B1](B1_COMPACTION_REPORT.md). Các số đo trong báo cáo
live cũ là của lần chạy đã lưu, không thay thế việc kiểm chứng giao diện hiện tại.

```powershell
python -m pytest -q --basetemp=data/pytest-b
```

### Bài tập mở rộng Challenge A

Web hiện là chat tự nhiên: nhập nội dung, **+ Session mới** để đổi phiên; nút
**Bằng chứng** mở tool/context và **Chế độ chụp ảnh** hiện quyết định ghi cùng
memory trước/sau. Không có nút kịch bản bắt buộc trong giao diện chat.
Xem [hướng dẫn nhập 5 câu và chụp ảnh](SCREENSHOT_GUIDE.md).
Trace chẩn đoán được lưu riêng dưới `data/sessions/traces/*.json`; lịch sử và
memory nghiệp vụ vẫn là Markdown. Trace không lưu API key/cấu hình client.

Kịch bản kiểm thử, cách chạy bằng Miniconda `SE373` và báo cáo giới hạn hiện tại:
[CHALLENGE_A_REPORT.md](CHALLENGE_A_REPORT.md). Kiểm thử bổ sung nằm ở
`tests/test_challenge_a.py`; các trường hợp `xfail` là lỗi đã biết, không phải PASS.

1. Vẽ lại cơ chế namespace → key → value của store.
2. Tắt `MEMORY_LONG_TERM` và giải thích vì sao agent không nhớ được quy ước khi đổi session.
3. Thêm nút "Quên tất cả memory của tôi" trong UI.
4. Tách memory theo user: đổi `USER_ID` và kiểm tra thư mục memory tách riêng.
5. Làm "memory tự động": harness tự trích quy ước từ hội thoại thay vì agent tự gọi tool — so sánh ưu/nhược.
6. Thêm chủ đề `conventions` lấy từ `AGENTS.md` và tự đồng bộ khi `AGENTS.md` đổi.

---

## 7. Câu hỏi thường gặp

**Agent quên mất quy ước sau khi đổi session — lỗi ở đâu?**
Kiểm tra: (1) `MEMORY_LONG_TERM` đang bật, (2) agent có thật sự gọi `remember` không
(in `/api/memory` hoặc `demo_cli.py memory`), (3) `USER_ID` có khác nhau không.

**Sau khi restart app, hội thoại cũ mất.**
Kiểm tra `data/sessions/<id>.md` còn tồn tại (agent nạp lại lịch sử từ file này mỗi lượt).

**Lịch sử dài làm context phình to.**
Bài lab không bật compaction (tóm tắt lịch sử) — cố ý, để tập trung vào memory dài hạn.
Nếu session thật sự dài, hãy xem lại slide "Memory curation" của lớp để cân nhắc thêm.
