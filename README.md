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
| Ghi | `remember(topic, content)` | thêm mục mới. Nếu trùng chủ đề với mục đang hiệu lực → **tự supersede mục cũ trước, rồi ghi mục mới** (`force=true` để giữ cả hai) |
| Đọc | `recall(topic?)` | nạp chi tiết khi thật cần |
| Sửa | `update(key, content)` | sửa nội dung, giữ nguyên `created_at` |
| Thay thế | `supersede(key, content)` | mục cũ → `status: superseded` + `superseded_by` + `superseded_at` (giữ nguồn, thời điểm) |
| Quên | `forget(key)` | xoá hẳn mục sai / lỗi thời |

> **Chống memory mâu thuẫn:** `remember` tự so nội dung mới với các mục đang hiệu lực
> trong cùng topic (trùng từ khóa). Nếu trùng → mục cũ được **supersede trước**
> (đánh dấu `superseded`, giữ nguồn + thời điểm), rồi mới ghi mục mới.
> Nhờ vậy không bao giờ có hai mục mâu thuẫn cùng hiệu lực, và không cần agent
> gọi thêm tool. Dùng `force=true` khi thật sự là hai quyết định khác nhau.
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

### Terminal

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

### Bài tập mở rộng

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
