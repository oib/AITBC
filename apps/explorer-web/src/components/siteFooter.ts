export function siteFooter(): string {
  const year = new Date().getFullYear();
  return `
    <footer class="site-footer">
      <div class="site-footer__inner">
        <p>&copy; ${year} AITBC Foundation. Explorer UI under active development.</p>
      </div>
    </footer>
  `;
}
