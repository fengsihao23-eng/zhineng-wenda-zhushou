import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

/** Render text/math without raw HTML, remote images, or model-generated navigation. */
export default function AnswerText({ content }: { content: string }) {
  return (
    <div className="answer-markdown">
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkMath]}
        rehypePlugins={[
          [
            rehypeKatex,
            { trust: false, strict: "ignore", throwOnError: false },
          ],
        ]}
        components={{
          a: ({ children }) => <span>{children}</span>,
          img: ({ alt }) => <span>{alt || "图片依据请从来源卡打开"}</span>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
