import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ParkField, parkFairPath } from './ParkField'
import type { StadiumLayout } from '@/types'

function fenwayLayout(): StadiumLayout {
  // Simplified Fenway: asymmetric corners, Green Monster in left
  const anchors: Array<[number, number]> = [
    [-45, 310], [-22.5, 379], [0, 420], [22.5, 380], [45, 302],
  ]
  return {
    stadium_id: 's1',
    name: 'Fenway Park',
    city: 'Boston',
    state: 'MA',
    roof_type: 'open',
    surface: 'grass',
    altitude_ft: 20,
    dimensions: {
      left_field: 310, left_center: 379, center_field: 420,
      right_center: 380, right_field: 302,
    },
    wall_points: Array.from({ length: 33 }, (_, i) => {
      const angle = -45 + (90 * i) / 32
      // linear interpolation between anchors (backend uses cosine; shape
      // detail doesn't matter for these tests)
      let dist = anchors[anchors.length - 1][1]
      for (let j = 0; j < anchors.length - 1; j++) {
        const [a0, d0] = anchors[j]
        const [a1, d1] = anchors[j + 1]
        if (angle >= a0 && angle <= a1) {
          dist = d0 + ((d1 - d0) * (angle - a0)) / (a1 - a0)
          break
        }
      }
      const theta = (angle * Math.PI) / 180
      return {
        angle_deg: angle,
        distance_ft: dist,
        x: 0.5 + (dist / 400) * Math.sin(theta),
        y: (dist / 400) * Math.cos(theta),
      }
    }),
    distance_markers: [
      { key: 'left_field', label: '310', distance_ft: 310, x: 0.05, y: 0.55 },
      { key: 'center_field', label: '420', distance_ft: 420, x: 0.5, y: 1.05 },
      { key: 'right_field', label: '302', distance_ft: 302, x: 0.93, y: 0.53 },
    ],
    feature_walls: [{ key: 'left_field', height_ft: 37.2, label: 'Left Field' }],
    features: ['Green Monster'],
    precision: 'visual_approximation',
  }
}

describe('parkFairPath', () => {
  it('starts at home plate and closes', () => {
    const d = parkFairPath(fenwayLayout(), 700, 700)
    expect(d.startsWith('M 350 700')).toBe(true)
    expect(d.endsWith('Z')).toBe(true)
  })
})

describe('ParkField', () => {
  it('renders the park name plate', () => {
    const { container } = render(
      <svg>
        <ParkField layout={fenwayLayout()} svgWidth={700} svgHeight={700} />
      </svg>
    )
    expect(container.textContent).toContain('Fenway Park')
    expect(container.textContent).toContain('Boston')
  })

  it('renders distance marker pills', () => {
    const { container } = render(
      <svg>
        <ParkField layout={fenwayLayout()} svgWidth={700} svgHeight={700} />
      </svg>
    )
    for (const label of ['310', '420', '302']) {
      expect(container.textContent).toContain(label)
    }
  })

  it('renders a feature wall with height label', () => {
    const { container } = render(
      <svg>
        <ParkField layout={fenwayLayout()} svgWidth={700} svgHeight={700} />
      </svg>
    )
    expect(container.textContent).toContain('37 ft')
    const monster = Array.from(container.querySelectorAll('polyline')).find(
      (p) => p.getAttribute('stroke') === '#1d5a36'
    )
    expect(monster).toBeTruthy()
  })

  it('skips feature walls below the visual threshold', () => {
    const layout = fenwayLayout()
    layout.feature_walls = [{ key: 'right_field', height_ft: 3, label: 'Right Field' }]
    const { container } = render(
      <svg>
        <ParkField layout={layout} svgWidth={700} svgHeight={700} />
      </svg>
    )
    expect(container.textContent).not.toContain('3 ft')
  })
})
