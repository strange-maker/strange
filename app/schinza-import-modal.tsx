"use client";

import { ChangeEvent, useMemo, useState } from "react";
import { api } from "./api-client";

type ManualSource = {
  id: string;
  source_name: string;
  source_type: string;
  crawl_method: string;
  adapter_status: string;
};

type PreviewItem = {
  title: string;
  original_url: string;
  published_at: string | null;
  source_name: string;
  topic_tags: string[];
  sales_relevance_score: number;
  display_title: string;
  requires_review: boolean;
  verification_notice: string;
};

type Preview = {
  total_count: number;
  missing_body_count: number;
  invalid_rows: { row: number; reason: string }[];
  file_sha256: string;
  items: PreviewItem[];
  limits: { max_file_bytes: number; max_records: number };
  credential_storage: false;
};

type ImportResult = {
  id: string;
  status: string;
  total_count: number;
  success_count: number;
  duplicate_count: number;
  failure_count: number;
  idempotent_replay: boolean;
};

const MAX_FILE_BYTES = 5_000_000;

export function SchinzaImportModal({
  sources,
  onClose,
  onDone,
}: {
  sources: ManualSource[];
  onClose: () => void;
  onDone: () => void;
}) {
  const eligible = useMemo(
    () =>
      sources.filter(
        (source) =>
          source.source_type === "wechat_manual" &&
          source.crawl_method === "manual_import" &&
          source.adapter_status === "manual_only",
      ),
    [sources],
  );
  const [sourceName, setSourceName] = useState(eligible[0]?.source_name ?? "");
  const [filename, setFilename] = useState("");
  const [contentText, setContentText] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setError("");
    setPreview(null);
    setResult(null);
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setFilename("");
      setContentText("");
      setError("文件超过 5 MB，请拆分后再导入。");
      event.target.value = "";
      return;
    }
    if (!/\.(json|csv)$/i.test(file.name)) {
      setFilename("");
      setContentText("");
      setError("仅支持 Schinza 导出的 JSON 或 CSV 文件。");
      event.target.value = "";
      return;
    }
    setFilename(file.name);
    setContentText(await file.text());
  };

  const requestPreview = async () => {
    if (!sourceName || !filename || !contentText) {
      setError("请选择公众号来源和本机导出文件。");
      return;
    }
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setPreview(
        await api<Preview>("/api/articles/manual-import/batch-preview", {
          method: "POST",
          body: JSON.stringify({
            filename,
            source_name: sourceName,
            content_text: contentText,
          }),
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预览失败");
    } finally {
      setBusy(false);
    }
  };

  const confirmImport = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      setResult(
        await api<ImportResult>("/api/articles/manual-import/batch", {
          method: "POST",
          body: JSON.stringify({
            filename,
            source_name: sourceName,
            content_text: contentText,
            expected_file_sha256: preview.file_sha256,
          }),
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量导入失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="overlay">
      <section className="modal schinza-modal" aria-modal="true" role="dialog">
        <div className="modal-head">
          <div>
            <small className="eyebrow">LOCAL SCHINZA EXPORT</small>
            <h2>Schinza 公众号批量导入</h2>
            <p>仅在浏览器读取本机导出文件，先预览校验，再由你明确确认导入。</p>
          </div>
          <button className="icon-btn" type="button" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="compliance">
          <b>安全边界</b>
          不上传或保存 uin、key、pass_ticket、appmsg_token、wxtoken、Cookie、证书或私钥。
          公众号内容固定为低可信线索，公众号线索，建议核验官方来源。
        </div>

        {error && <div className="login-error">{error}</div>}
        {result && (
          <div className="schinza-result">
            <b>{result.idempotent_replay ? "该文件已导入过" : "导入完成"}</b>
            <span>
              成功 {result.success_count} · 去重 {result.duplicate_count} · 失败{" "}
              {result.failure_count}
            </span>
          </div>
        )}

        <div className="form-grid">
          <label>
            归属公众号来源
            <select
              value={sourceName}
              onChange={(event) => {
                setSourceName(event.target.value);
                setPreview(null);
              }}
              disabled={busy || Boolean(result)}
            >
              {eligible.map((source) => (
                <option key={source.id}>{source.source_name}</option>
              ))}
            </select>
          </label>
          <label>
            Schinza 导出文件
            <input
              type="file"
              accept=".json,.csv,application/json,text/csv"
              onChange={(event) => void readFile(event)}
              disabled={busy || Boolean(result)}
            />
          </label>
        </div>

        {preview && !result && (
          <>
            <div className="schinza-summary">
              <div>
                <span>有效记录</span>
                <strong>{preview.total_count}</strong>
              </div>
              <div>
                <span>正文缺失</span>
                <strong>{preview.missing_body_count}</strong>
              </div>
              <div>
                <span>无效行</span>
                <strong>{preview.invalid_rows.length}</strong>
              </div>
              <div>
                <span>文件指纹</span>
                <code>{preview.file_sha256.slice(0, 12)}…</code>
              </div>
            </div>
            <div className="schinza-preview-list">
              {preview.items.slice(0, 12).map((item, index) => (
                <article key={`${item.original_url}-${index}`}>
                  <div>
                    <span className="badge bad">低可信</span>
                    <span className="badge neutral">
                      销售分 {item.sales_relevance_score}
                    </span>
                    {item.topic_tags.map((tag) => (
                      <span className="badge neutral" key={tag}>
                        {tag}
                      </span>
                    ))}
                  </div>
                  <b>{item.display_title || item.title}</b>
                  <small>
                    {item.published_at || "发布时间待核验"} ·{" "}
                    {item.verification_notice}
                  </small>
                </article>
              ))}
            </div>
            {preview.invalid_rows.length > 0 && (
              <details className="schinza-errors">
                <summary>查看 {preview.invalid_rows.length} 条无效记录</summary>
                {preview.invalid_rows.map((item) => (
                  <p key={`${item.row}-${item.reason}`}>
                    第 {item.row} 行：{item.reason}
                  </p>
                ))}
              </details>
            )}
          </>
        )}

        <div className="modal-actions">
          <button className="btn" type="button" onClick={onClose}>
            {result ? "关闭" : "取消"}
          </button>
          {!preview && !result && (
            <button
              className="btn primary"
              type="button"
              onClick={() => void requestPreview()}
              disabled={busy || !sourceName || !filename}
            >
              {busy ? "校验中…" : "预览并校验"}
            </button>
          )}
          {preview && !result && (
            <button
              className="btn primary"
              type="button"
              onClick={() => void confirmImport()}
              disabled={busy}
            >
              {busy ? "导入中…" : `确认导入 ${preview.total_count} 条`}
            </button>
          )}
          {result && (
            <button className="btn primary" type="button" onClick={onDone}>
              刷新工作台
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
