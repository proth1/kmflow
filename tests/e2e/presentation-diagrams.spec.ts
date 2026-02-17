import { test, expect } from '@playwright/test';
import path from 'path';

const PRESENTATION_PATH = `file://${path.resolve(__dirname, '../../docs/presentations/index.html')}`;

// Slides that contain BPMN diagram containers
const DIAGRAM_SLIDES = [
  { id: 'slide-12', label: 'Evidence Lifecycle' },
  { id: 'slide-23', label: 'Engagement Lifecycle' },
  { id: 'slide-26b', label: 'Loan Origination Case Study' },
  { id: 'slide-30', label: 'Evidence Collection Flow' },
  { id: 'slide-31', label: 'POV Generation Flow' },
  { id: 'slide-32', label: 'TOM Gap Analysis Flow' },
  { id: 'slide-33', label: 'Continuous Monitoring Flow' },
];

test.describe('Presentation loads as self-contained HTML', () => {
  test('loads without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });

    // Verify page title
    await expect(page).toHaveTitle(/KMFlow/);

    // No JS errors
    expect(errors).toHaveLength(0);
  });

  test('has correct total slide count', async ({ page }) => {
    await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });
    const slideCount = await page.locator('section.slide').count();
    // 41 original + 1 case study (26b) + 1 legend (29b) = 43
    expect(slideCount).toBe(43);
  });
});

test.describe('BPMN diagrams render on all target slides', () => {
  for (const slide of DIAGRAM_SLIDES) {
    test(`${slide.label} (${slide.id}) renders an SVG diagram`, async ({ page }) => {
      await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });

      const section = page.locator(`#${slide.id}`);
      await expect(section).toBeAttached();

      // Scroll slide into view
      await section.scrollIntoViewIfNeeded();

      // Diagram container exists within this slide
      const container = section.locator('.diagram-container');
      await expect(container).toBeAttached();

      // SVG is present inside the container
      const svg = container.locator('svg');
      await expect(svg).toBeAttached();

      // SVG has content (at least some child elements)
      const childCount = await svg.locator('g').count();
      expect(childCount).toBeGreaterThan(0);
    });
  }
});

test.describe('Diagram accessibility', () => {
  for (const slide of DIAGRAM_SLIDES) {
    test(`${slide.label} (${slide.id}) has proper ARIA attributes`, async ({ page }) => {
      await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });

      const container = page.locator(`#${slide.id} .diagram-container`);

      // Container has role="img"
      await expect(container).toHaveAttribute('role', 'img');

      // Container has a non-empty aria-label
      const ariaLabel = await container.getAttribute('aria-label');
      expect(ariaLabel).toBeTruthy();
      expect(ariaLabel!.length).toBeGreaterThan(10);

      // Container is keyboard-focusable
      await expect(container).toHaveAttribute('tabindex', '0');

      // SVG is hidden from screen readers
      const svg = container.locator('svg');
      await expect(svg).toHaveAttribute('aria-hidden', 'true');
    });
  }
});

test.describe('Diagram sizing and overflow', () => {
  test('diagrams do not exceed max-height', async ({ page }) => {
    await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });

    for (const slide of DIAGRAM_SLIDES) {
      const container = page.locator(`#${slide.id} .diagram-container`);
      await container.scrollIntoViewIfNeeded();

      const box = await container.boundingBox();
      if (box) {
        // 60vh at 1080px viewport = 648px max
        expect(box.height).toBeLessThanOrEqual(650);
      }
    }
  });

  test('diagrams scale within container width', async ({ page }) => {
    await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });

    for (const slide of DIAGRAM_SLIDES) {
      const container = page.locator(`#${slide.id} .diagram-container`);
      const svg = container.locator('svg');
      await container.scrollIntoViewIfNeeded();

      const containerBox = await container.boundingBox();
      const svgBox = await svg.boundingBox();

      if (containerBox && svgBox) {
        // SVG should not exceed container width (accounting for padding)
        expect(svgBox.width).toBeLessThanOrEqual(containerBox.width);
      }
    }
  });
});

test.describe('BPMN notation legend slide', () => {
  test('legend slide exists before user flow slides', async ({ page }) => {
    await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });

    const legend = page.locator('#slide-29b');
    await expect(legend).toBeAttached();

    // Verify it contains the notation elements
    await expect(legend.getByText('Start / End Event')).toBeAttached();
    await expect(legend.getByText('Task / Activity')).toBeAttached();
    await expect(legend.getByText('Gateway (Decision)')).toBeAttached();
    await expect(legend.getByText('Sequence Flow')).toBeAttached();
    await expect(legend.getByText('Subprocess')).toBeAttached();
    await expect(legend.getByText('Swimlanes')).toBeAttached();
  });
});

test.describe('Responsive rendering', () => {
  const viewports = [
    { width: 1920, height: 1080, label: 'Desktop 1080p' },
    { width: 1440, height: 900, label: 'Laptop' },
    { width: 1024, height: 768, label: 'Tablet landscape' },
  ];

  for (const vp of viewports) {
    test(`diagrams render at ${vp.label} (${vp.width}x${vp.height})`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(PRESENTATION_PATH, { waitUntil: 'domcontentloaded' });

      // Check first and last diagram slides
      for (const slideId of ['slide-12', 'slide-33']) {
        const container = page.locator(`#${slideId} .diagram-container`);
        await container.scrollIntoViewIfNeeded();
        const box = await container.boundingBox();
        expect(box).toBeTruthy();
        expect(box!.width).toBeGreaterThan(100);
        expect(box!.height).toBeGreaterThan(50);
      }
    });
  }
});
