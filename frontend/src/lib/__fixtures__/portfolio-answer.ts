/**
 * The shape of a real answer a model wrote in this product (a review of a portfolio page), kept as a test fixture because it is exactly the kind
 * of text that showed as clutter: a bold line as a title, a three-column table with bold labels, code and citations inside its cells, a `###`
 * heading, a numbered list mixing "**Title** – text" with "**bold phrase** continuing text", lines ending in two spaces, and a closing paragraph.
 */
export const PORTFOLIO_REF = "tool:web/fetch:b837a4efce56:portfolio-g9av.onrender.com-f83a719872";

export const PORTFOLIO_ANSWER = `**Findings from the portfolio page (https://portfolio-g9av.onrender.com/)**

| Area | Observation (potential fault) | Evidence from the page |
|------|------------------------------|------------------------|
| **Redundant / duplicated navigation** | The main navigation items appear twice in the markup (\`About Experience Work\`). This can confuse screen‑readers. | “About Experience Work … About Experience Work” [[${PORTFOLIO_REF}]] |
| **Unclear placeholder** | A stray “0%” appears at the very top of the page. | “0%” at the start of the document [[${PORTFOLIO_REF}]] |
| **Unexplained “SM.” label** | The text “SM.” appears under the title. | “SM.” appears right after the title [[${PORTFOLIO_REF}]] |

### Summary & Recommendations

1. **Clean up duplicated navigation and skill lists** – keep a single navigation bar.
2. **Remove or fix stray UI elements** – the “0%” and “SM.” texts should be removed.
3. **Add descriptive \`alt\` attributes** to all images and icons.

Because the source does not contain any CSS, we cannot assess the colours.`;
