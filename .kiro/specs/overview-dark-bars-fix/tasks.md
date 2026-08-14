# Implementation Plan: Remove Dark Background Bars in Overview Page

## Overview

This implementation removes dark background bars from system information rows in the Overview page's left panel and increases vertical spacing between rows. The approach uses QSS (Qt Style Sheets) modifications as the primary solution, with Python layout adjustments as a fallback option if needed.

## Tasks

- [x] 1. Modify QSS styles to remove dark backgrounds and increase spacing
  - Locate `QLabel#InfoKey` and `QLabel#InfoValue` rules in `styles.qss` (around lines 403-406)
  - Add `background-color: transparent;` to both `#InfoKey` and `#InfoValue` selectors
  - Add `padding: 4px 0px;` to both selectors to increase vertical spacing
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 2. Visual verification and testing
  - [-] 2.1 Perform manual visual inspection
    - Launch application and navigate to Overview tab
    - Verify dark backgrounds are removed from info rows
    - Verify vertical spacing has increased between rows
    - Confirm text remains readable and properly aligned
    - _Requirements: 2.1, 2.2, 2.3_
  
  - [x] 2.2 Verify isolation (no unintended changes)
    - Check all other tabs to ensure styling remains unchanged
    - Verify other label types (SpecCardTitle, TabSectionTitle) retain original styling
    - Test window resizing to confirm layout consistency
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [~] 3. Checkpoint - Evaluate results
  - If visual results are satisfactory, mark task complete
  - If spacing is insufficient, proceed to Task 4 for Python layout adjustment
  - Ask the user if questions or adjustments are needed

- [~] 4. (Fallback) Adjust Python layout spacing if QSS changes are insufficient
  - Open `tabs/overview.py` and locate the info_grid layout section
  - Modify `info_grid.setVerticalSpacing()` from 6 to 10 or 12 pixels
  - Re-test visually to verify improved spacing
  - _Requirements: 2.1, 2.2_

## Notes

- Task 1 is the primary solution using declarative QSS styling
- Task 2 requires manual visual testing as this is a UI styling change
- Task 3 is a decision checkpoint to determine if Task 4 is needed
- Task 4 is optional and only needed if QSS padding alone is insufficient
- No unit tests or property-based tests are included as this is purely a visual styling change
- Testing focuses on visual verification and regression prevention (ensuring other elements remain unaffected)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["4"] }
  ]
}
```
