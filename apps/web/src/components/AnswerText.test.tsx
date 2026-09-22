import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import AnswerText from "./AnswerText";

describe("safe educational answer rendering", () => {
  it("does not render raw HTML, external images, or model-generated links", () => {
    const html = renderToStaticMarkup(
      <AnswerText
        content={
          "<script>alert(1)</script>\n\n![diagram](https://example.com/pixel)\n\n[link](javascript:alert(1))\n\n[external](https://example.com)"
        }
      />,
    );
    expect(html).not.toMatch(/<(script|img|a)\b/);
    expect(html).not.toContain("href=");
    expect(html).not.toContain("src=");
  });
  it("renders basic Markdown and math while keeping untrusted formula commands inert", () => {
    const html = renderToStaticMarkup(
      <AnswerText
        content={"**结论**\n\n$x^2 + 1$\n\n$\\href{javascript:alert(1)}{x}$"}
      />,
    );
    expect(html).toContain("<strong>结论</strong>");
    expect(html).toContain("katex");
    expect(html).not.toMatch(/<a\b/);
  });
});
