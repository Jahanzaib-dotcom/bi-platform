/**
 * Frontend component tests for:
 *   - StatCard
 *   - Badge
 *   - ScoreRing
 *   - DashboardLayout (navigation)
 */

import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';

// ---------------------------------------------------------------------------
// Mock dependencies that are not relevant to component logic
// ---------------------------------------------------------------------------

// framer-motion — replace with passthrough div to avoid animation complexity
jest.mock('framer-motion', () => {
  const React = require('react');
  const Actual = jest.requireActual('framer-motion');
  return {
    ...Actual,
    motion: new Proxy(
      {},
      {
        get: (_: object, tag: string) =>
          // eslint-disable-next-line react/display-name
          React.forwardRef(
            ({ children, ...props }: React.HTMLAttributes<HTMLElement>, ref: React.Ref<unknown>) =>
              React.createElement(tag, { ...props, ref }, children)
          ),
      }
    ),
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    useAnimation: () => ({ start: jest.fn() }),
    useInView: () => true,
  };
});

// react-countup — just render the end value as plain text
jest.mock('react-countup', () => {
  const React = require('react');
  interface CountUpProps {
    end: number;
    decimals?: number;
    separator?: string;
    prefix?: string;
    suffix?: string;
  }
  const CountUp = ({ end, decimals = 0 }: CountUpProps) => (
    <span data-testid="countup-value">{end.toFixed(decimals)}</span>
  );
  CountUp.displayName = 'CountUp';
  return CountUp;
});

// lucide-react icons — render a minimal svg so layout is predictable
jest.mock('lucide-react', () => {
  const React = require('react');
  const Icon = ({ size }: { size?: number }) => (
    <svg data-testid="icon" width={size} height={size} />
  );
  Icon.displayName = 'Icon';
  return new Proxy(
    {},
    { get: () => Icon }
  );
});

// next/navigation
jest.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({ push: jest.fn() }),
}));

// next/link
jest.mock('next/link', () => {
  const React = require('react');
  const Link = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  Link.displayName = 'Link';
  return Link;
});

// zustand auth store
jest.mock('@/store', () => ({
  useAuthStore: () => ({
    user: { fullName: 'Test User', email: 'test@example.com' },
    logout: jest.fn(),
  }),
  useUIStore: () => ({
    sidebarCollapsed: false,
  }),
}));

// ---------------------------------------------------------------------------
// Component imports (after mocks are set up)
// ---------------------------------------------------------------------------

import StatCard from '../components/ui/StatCard';
import Badge from '../components/ui/Badge';
import ScoreRing from '../components/ui/ScoreRing';
import DashboardLayout from '../components/layouts/DashboardLayout';

// ---------------------------------------------------------------------------
// StatCard
// ---------------------------------------------------------------------------

describe('StatCard', () => {
  it('renders the label', () => {
    render(<StatCard label="Total Businesses" value={42} />);
    expect(screen.getByText('Total Businesses')).toBeInTheDocument();
  });

  it('renders the numeric value via CountUp', () => {
    render(<StatCard label="Revenue" value={1500} />);
    expect(screen.getByTestId('countup-value')).toHaveTextContent('1500');
  });

  it('renders a prefix when supplied', () => {
    render(<StatCard label="Amount" value={99} prefix="$" />);
    expect(screen.getByText('$')).toBeInTheDocument();
  });

  it('renders a suffix when supplied', () => {
    render(<StatCard label="Rate" value={75} suffix="%" />);
    expect(screen.getByText('%')).toBeInTheDocument();
  });

  it('shows a positive change badge with + sign', () => {
    render(<StatCard label="Growth" value={10} change={5} />);
    expect(screen.getByText('+5%')).toBeInTheDocument();
  });

  it('shows a negative change badge', () => {
    render(<StatCard label="Decline" value={5} change={-3} />);
    expect(screen.getByText('-3%')).toBeInTheDocument();
  });

  it('shows neutral indicator for zero change', () => {
    render(<StatCard label="Steady" value={0} change={0} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('renders without a change prop (no trend badge)', () => {
    const { container } = render(<StatCard label="Count" value={7} />);
    // No +/- badge should be present
    expect(container.querySelector('[class*="emerald"]')).toBeNull();
    expect(container.querySelector('[class*="red"]')).toBeNull();
  });

  it('renders the icon slot when provided', () => {
    const icon = <span data-testid="custom-icon">★</span>;
    render(<StatCard label="Stars" value={5} icon={icon} />);
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('renders decimal values correctly', () => {
    render(<StatCard label="Avg Score" value={73.4} decimals={1} />);
    expect(screen.getByTestId('countup-value')).toHaveTextContent('73.4');
  });
});

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>Active</Badge>);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('applies success variant classes', () => {
    const { container } = render(<Badge variant="success">OK</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/emerald/);
  });

  it('applies danger variant classes', () => {
    const { container } = render(<Badge variant="danger">Error</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/red/);
  });

  it('applies warning variant classes', () => {
    const { container } = render(<Badge variant="warning">Warn</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/amber/);
  });

  it('applies info variant classes', () => {
    const { container } = render(<Badge variant="info">Info</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/sky/);
  });

  it('applies purple variant classes', () => {
    const { container } = render(<Badge variant="purple">New</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/purple/);
  });

  it('applies slate variant classes', () => {
    const { container } = render(<Badge variant="slate">Neutral</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/slate/);
  });

  it('renders a dot when dot=true', () => {
    const { container } = render(<Badge dot>With Dot</Badge>);
    // The dot is a sibling span with rounded-full
    const spans = container.querySelectorAll('span');
    expect(spans.length).toBeGreaterThanOrEqual(2);
  });

  it('does NOT render a dot when dot=false (default)', () => {
    render(<Badge>No Dot</Badge>);
    // Only one text node child — no extra dot span
    const badge = screen.getByText('No Dot');
    expect(badge.parentElement?.querySelectorAll('span').length).toBeLessThanOrEqual(1);
  });

  it('applies sm size styles', () => {
    const { container } = render(<Badge size="sm">Small</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/px-1\.5/);
  });

  it('applies md size styles (default)', () => {
    const { container } = render(<Badge size="md">Medium</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/px-2\.5/);
  });
});

// ---------------------------------------------------------------------------
// ScoreRing
// ---------------------------------------------------------------------------

describe('ScoreRing', () => {
  it('renders the score value in the SVG text element', () => {
    render(<ScoreRing score={75} animate={false} />);
    const textEl = document.querySelector('text');
    expect(textEl?.textContent).toBe('75');
  });

  it('clamps scores above 100 to 100', () => {
    render(<ScoreRing score={150} animate={false} />);
    const textEl = document.querySelector('text');
    expect(textEl?.textContent).toBe('100');
  });

  it('clamps scores below 0 to 0', () => {
    render(<ScoreRing score={-10} animate={false} />);
    const textEl = document.querySelector('text');
    expect(textEl?.textContent).toBe('0');
  });

  it('renders a label when supplied', () => {
    render(<ScoreRing score={50} label="SEO Score" animate={false} />);
    expect(screen.getByText('SEO Score')).toBeInTheDocument();
  });

  it('does not render a label when not supplied', () => {
    render(<ScoreRing score={50} animate={false} />);
    expect(screen.queryByText('SEO Score')).not.toBeInTheDocument();
  });

  it('hides the value when showValue=false', () => {
    render(<ScoreRing score={80} showValue={false} animate={false} />);
    expect(document.querySelector('text')).not.toBeInTheDocument();
  });

  it('renders an SVG element', () => {
    render(<ScoreRing score={60} animate={false} />);
    expect(document.querySelector('svg')).toBeInTheDocument();
  });

  it('uses a green gradient for high scores (>=70)', () => {
    render(<ScoreRing score={90} animate={false} />);
    const stopGreen = document.querySelector('#scoreGradientGreen');
    expect(stopGreen).toBeInTheDocument();
  });

  it('uses a yellow gradient for medium scores (40-69)', () => {
    render(<ScoreRing score={55} animate={false} />);
    const stopYellow = document.querySelector('#scoreGradientYellow');
    expect(stopYellow).toBeInTheDocument();
  });

  it('uses a red gradient for low scores (<40)', () => {
    render(<ScoreRing score={20} animate={false} />);
    const stopRed = document.querySelector('#scoreGradientRed');
    expect(stopRed).toBeInTheDocument();
  });

  it('respects a custom size prop', () => {
    render(<ScoreRing score={50} size={120} animate={false} />);
    const svg = document.querySelector('svg');
    expect(svg).toHaveAttribute('width', '120');
    expect(svg).toHaveAttribute('height', '120');
  });
});

// ---------------------------------------------------------------------------
// DashboardLayout — navigation
// ---------------------------------------------------------------------------

describe('DashboardLayout', () => {
  const renderLayout = (children: React.ReactNode = <div>page content</div>) =>
    render(<DashboardLayout>{children}</DashboardLayout>);

  it('renders the BI Platform branding text in the sidebar', () => {
    renderLayout();
    expect(screen.getAllByText(/BI Platform/i).length).toBeGreaterThan(0);
  });

  it('renders all main navigation items', () => {
    renderLayout();
    const navLabels = [
      'Dashboard',
      'Command Center',
      'Discovery',
      'Audit Center',
      'Lead Intelligence',
      'Analytics',
      'Settings',
    ];
    for (const label of navLabels) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it('renders children inside the layout', () => {
    renderLayout(<div data-testid="page">Hello World</div>);
    expect(screen.getAllByTestId('page').length).toBeGreaterThan(0);
  });

  it('renders the user full name from the auth store', () => {
    renderLayout();
    expect(screen.getAllByText('Test User').length).toBeGreaterThan(0);
  });

  it('renders navigation links with correct hrefs', () => {
    renderLayout();
    const links = document.querySelectorAll('a[href="/dashboard"]');
    expect(links.length).toBeGreaterThan(0);
  });

  it('renders a logout button', () => {
    renderLayout();
    // LogOut icon or button with title "Sign out"
    const logoutButtons = screen.queryAllByTitle('Sign out');
    // May appear in both desktop and mobile sidebars
    expect(logoutButtons.length).toBeGreaterThanOrEqual(1);
  });
});
