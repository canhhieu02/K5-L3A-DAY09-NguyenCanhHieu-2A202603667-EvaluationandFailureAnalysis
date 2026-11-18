# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

---

## Chi tiết Case phân tích

| Trường | Nội dung |
|---|---|
| **Trial** | `seeded_regression C-002@11` |
| **Triệu chứng** | Grader Lab 8 báo FAIL: `status resolved != denied`. Grader `RefundAmountCorrect` báo FAIL: `ledger 20000 != expected 0`. Grader `DbFactKept` báo FAIL: phát hiện event `model_override`. Sổ cái (ledger) ghi nhận hoàn tiền 20.000đ (`refund_count=1`) trong khi nhãn kỳ vọng hoàn 0đ (`status=denied`). Reply văn bản báo: *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* |
| **Bước sai đầu tiên** | **Event số 3 — `model_override`**: `{"delay_days": 5}` |
| **Vì sao là bước *đầu tiên*** | • **Event 1 (`handoff`)**: Tạo ngữ cảnh ủy quyền kiểm tra chính sách cho claim C-002 chính xác.<br>• **Event 2 (`investigator`)**: Công cụ `lookup_order` tra cứu DB trả về thông tin đơn hàng O-202 chính xác từ cơ sở dữ liệu (`status: delivered`, `delay_days: 0`).<br>• Đến **Event 3**, agent tin theo nội dung ticket của khách hàng ("Đơn giao trễ 5 ngày...") và thực hiện đè giá trị `delay_days = 5` lên giá trị thực tế của DB. Các bước tiếp theo (Event 4 tính quote 20.000đ theo clause `SHIP-LATE-03`, Event 5 tra cứu lịch sử, Event 6 hoàn tiền và reply) đều là hệ quả sai dây chuyền từ Event 3. |
| **Failure mode** | **`FM-03` (`ticket_trust`)** — Tin ticket hơn DB. |
| **Đối chứng (`fixed`)** | Trên cùng `C-002@11` với shape `fixed`, agent kích hoạt cờ `no_override`: không có Event `model_override`. Sau Event 2 tra cứu DB (`delay_days = 0`), Event 3 tính quote ra `amount_vnd: 0` (`no_entitlement`), Event 4 đưa ra câu trả lời từ chối chính xác: *"Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành."* Ledger không có giao dịch (`refund_vnd = 0`, `status = denied`), khớp hoàn toàn với nhãn mong đợi. |
| **Regression test** | • `test_override_event_breaks_db_fact` trong `tests/test_lab9_graders.py` (khẳng định grader `DbFactKept` bắt được event `model_override`).<br>• `test_wrong_amount_in_ledger` trong `tests/test_lab9_graders.py` (khẳng định grader `RefundAmountCorrect` bắt được số tiền hoàn sai trong ledger).<br>• Đã xác nhận: Bị fail trên `seeded_regression` và pass trên `fixed`. |
| **Chưa chắc chắn** | Trace log chứng minh được hành vi ghi đè dữ liệu `model_override`, nhưng không phản ánh được nguyên nhân nội tại bên trong trọng số LLM: liệu mô hình bị prompt injection cố tình hay do nhiệt độ (temperature) / prompt trích xuất chưa đủ tính nghiêm ngặt để phân biệt giữa dữ liệu có thẩm quyền (ground truth DB) và lời khai từ khách hàng. |

---

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
