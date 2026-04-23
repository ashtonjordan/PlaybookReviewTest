/**
 * Agent Desktop RSS Feed Widget
 *
 * A simple widget that displays an RSS feed inside the
 * Webex Contact Center Agent Desktop.
 */

class RSSFeedWidget extends HTMLElement {
  connectedCallback() {
    const feedUrl = this.getAttribute("feed-url");
    this.innerHTML = `<div class="rss-widget"><p>Loading feed...</p></div>`;
    this.loadFeed(feedUrl);
  }

  async loadFeed(url) {
    try {
      const response = await fetch(url);
      const text = await response.text();
      const parser = new DOMParser();
      const xml = parser.parseFromString(text, "text/xml");
      const items = xml.querySelectorAll("item");

      let html = "<ul>";
      items.forEach((item) => {
        const title = item.querySelector("title").textContent;
        const link = item.querySelector("link").textContent;
        html += `<li><a href="${link}" target="_blank">${title}</a></li>`;
      });
      html += "</ul>";

      this.querySelector(".rss-widget").innerHTML = html;
    } catch (err) {
      this.querySelector(".rss-widget").innerHTML =
        `<p>Error loading feed: ${err.message}</p>`;
    }
  }
}

customElements.define("widget-rss-feed", RSSFeedWidget);
