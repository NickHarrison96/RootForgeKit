# Design Document

## Overview

This design document specifies the technical solution for removing dark background bars from system information rows in the Overview page's left panel and increasing vertical spacing between rows. The implementation involves targeted QSS (Qt Style Sheets) modifications and potential Python layout adjustments.

## Architecture

The solution follows a **declarative styling approach** where visual changes are primarily implemented through QSS modifications. This approach ensures:
- Clear separation between presentation (QSS) and logic (Python)
- Easy maintainability and future style adjustments
- Minimal code changes in the Python layer
- Consistent styling behavior across the application

### Component Overview

```
OverviewTab (QWidget)
├── Left Panel (QFrame#OverviewLeftPanel)
│   └── Info Grid (QGridLayout)
│       ├── InfoKey Labels (QLabel#InfoKey) [Row captions]
│       └── InfoValue Labels (QLabel#InfoValue) [Data values]
└── Right Panel (Widget Cards)
```

## Components

### 1. QSS Style Sheet (`styles.qss`)

**Purpose**: Define visual styling for UI elements using Qt Style Sheets

**Current State**:
```css
QLabel#InfoKey { 
    color: #00f0ff; 
}

QLabel#InfoValue { 
    color: #c9d1d9; 
}
```

**Proposed Changes**:
The `InfoKey` and `InfoValue` labels currently inherit no explicit background styling in the general QLabel rule, but the issue description indicates dark backgrounds are visible. The solution involves:

1. **Remove/Override Dark Backgrounds**: Explicitly set transparent backgrounds
2. **Increase Vertical Spacing**: Add padding to create more vertical space

**Modified Styling**:
```css
QLabel#InfoKey {
    color: #00f0ff;
    background-color: transparent;
    padding: 4px 0px;  /* Vertical padding for spacing */
}

QLabel#InfoValue {
    color: #c9d1d9;
    background-color: transparent;
    padding: 4px 0px;  /* Vertical padding for spacing */
}
```

**Rationale**:
- `background-color: transparent` explicitly removes any inherited dark backgrounds
- `padding: 4px 0px` adds 4 pixels of vertical padding (top and bottom), effectively creating 8 pixels between rows
- Horizontal padding is set to 0 to maintain current alignment

### 2. Overview Tab Layout (`tabs/overview.py`)

**Purpose**: Construct the left panel info grid and manage system data display

**Current Implementation Analysis**:
```python
info_grid = QGridLayout(info_container)
info_grid.setContentsMargins(4, 4, 6, 4)
info_grid.setHorizontalSpacing(12)
info_grid.setVerticalSpacing(6)  # Current: 6 pixels
```

**Proposed Changes**:

**Option A: QSS-Only Solution (Recommended)**
- Keep Python layout code unchanged
- Rely entirely on QSS padding to increase spacing
- Advantage: Minimal code changes, pure styling modification

**Option B: Combined Python + QSS Solution**
- Increase `setVerticalSpacing()` value in addition to QSS padding
- Modify to: `info_grid.setVerticalSpacing(10)` or `12`
- Advantage: More control over exact spacing

**Recommendation**: Start with **Option A** (QSS-only). If visual results are insufficient, proceed to **Option B**.

```python
# No Python changes needed for Option A

# Option B (if needed):
info_grid.setVerticalSpacing(10)  # Increased from 6 to 10
```

## Data Models

No data model changes required. This is a purely presentational modification affecting styling only.

## Interfaces

### Modified QSS Selectors

#### `QLabel#InfoKey`
- **Properties**: `color`, `background-color`, `padding`
- **Scope**: All labels with objectName "InfoKey" (row captions in left panel)
- **Behavior**: Displays text with transparent background and increased vertical padding

#### `QLabel#InfoValue`
- **Properties**: `color`, `background-color`, `padding`
- **Scope**: All labels with objectName "InfoValue" (data values in left panel)
- **Behavior**: Displays text with transparent background and increased vertical padding

### Unaffected Components

The following components should remain unchanged:
- `QFrame#OverviewLeftPanel`: Container background (#151c28) and border styling
- Right panel widget cards
- Other tabs and pages
- All other label types (SpecCardTitle, TabSectionTitle, etc.)

## Error Handling

This is a styling change with minimal error surface:

1. **QSS Parsing Errors**: If QSS syntax is invalid, PyQt6 will log warnings but continue with default styling. Validation: Manual syntax check before deployment.

2. **Visual Regression**: If changes inadvertently affect other UI elements:
   - Detection: Visual inspection of all tabs during testing
   - Mitigation: Ensure selectors are specific (`#InfoKey`, `#InfoValue`)
   - Rollback: Revert QSS changes if issues detected

3. **Spacing Too Large/Small**: If padding values produce undesirable spacing:
   - Solution: Iteratively adjust padding values (try 3px, 4px, 5px, 6px)
   - Fallback: Use Option B (Python layout spacing adjustment)

## Testing Strategy

Given this is a visual styling bugfix with no complex logic, the testing approach focuses on **visual verification** and **isolation validation**:

### Manual Visual Testing
1. **Primary Verification**: Launch application → Navigate to Overview tab → Verify:
   - No dark backgrounds visible on info rows
   - Increased vertical spacing between rows
   - Text remains readable and properly aligned
   
2. **Isolation Verification**: Check all other tabs/pages to ensure no unintended styling changes

3. **Responsive Behavior**: Resize window to verify layout maintains consistency at different sizes

### Example-Based Unit Tests

While most validation is visual, we can include minimal unit tests:

```python
def test_info_row_spacing_consistency():
    """Verify all info rows have consistent spacing"""
    # Create Overview tab instance
    # Check that all InfoKey/InfoValue labels have same padding property
    # Verify grid vertical spacing is consistent
```

```python
def test_other_elements_unaffected():
    """Verify changes don't affect other UI elements"""
    # Sample other label types (SpecCardTitle, TabSectionTitle)
    # Verify they retain their original styling
```

### Integration Test

```python
def test_overview_renders_without_errors():
    """Basic smoke test that Overview tab renders successfully"""
    # Create QApplication instance
    # Instantiate OverviewTab
    # Verify no exceptions during initialization
    # Verify all expected widgets are created
```

**Note**: Property-based testing is not applicable here as this is a static styling change with no varying inputs or behavioral logic to test across multiple iterations.

## Implementation Steps

### Step 1: Modify QSS Styles
1. Open `styles.qss`
2. Locate the `QLabel#InfoKey` and `QLabel#InfoValue` rules (around line 403-406)
3. Add `background-color: transparent;` to both rules
4. Add `padding: 4px 0px;` to both rules
5. Save file

### Step 2: Test Visual Changes
1. Run application
2. Navigate to Overview tab
3. Visually inspect left panel info rows
4. Verify dark backgrounds are removed
5. Verify spacing appears increased

### Step 3: Adjust if Needed
- If spacing is insufficient: Increase padding to `5px 0px` or `6px 0px`
- If QSS approach is insufficient: Implement Option B (modify Python layout spacing)

### Step 4: Validation Testing
1. Check all other tabs for unintended style changes
2. Test on different screen sizes/resolutions
3. Verify text remains readable and aligned

## Deployment

**Files Modified**:
- `styles.qss` (primary change)
- `tabs/overview.py` (only if Option B is needed)

**Rollback Plan**:
- Revert QSS changes by removing added properties
- If Python changes were made, revert those as well

**Deployment Risk**: **Very Low**
- Changes are isolated to specific UI elements
- No logic or data handling modifications
- Easy to test and verify visually
- Simple rollback if issues occur

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Analysis

After reviewing all acceptance criteria, **no properties suitable for property-based testing** were identified. This bugfix involves:

- **Static styling changes**: Background colors and padding values are constant, not variable across inputs
- **Visual verification**: The primary validation is visual inspection of rendered UI elements
- **Configuration checks**: Verifying QSS properties and Python layout settings are one-time checks
- **Isolation testing**: Ensuring other elements are unaffected requires checking specific examples, not universal properties

The acceptance criteria classify as:
- **SMOKE tests**: One-time checks for styling properties, implementation approach, and visual layout
- **EXAMPLE tests**: Verifying specific elements maintain their styling
- **INTEGRATION tests**: Ensuring application startup and tab isolation work correctly

**Property-based testing is not applicable** because:
1. There is no behavioral logic that varies with different inputs
2. Styling values are constant (background: transparent, padding: 4px)
3. 100 iterations would not reveal more issues than 1-2 visual checks
4. This tests UI rendering, not algorithmic correctness

### Testing Approach

Instead of property-based tests, this bugfix requires:

1. **Manual visual inspection** (primary validation method)
2. **Example-based unit tests** for specific elements
3. **Integration smoke test** for application startup
4. **Regression testing** to ensure other tabs remain unaffected

This approach is appropriate for UI styling modifications where visual verification is the primary correctness criterion.

## Future Considerations

### Theming System
If the application evolves to support multiple themes (light mode, custom color schemes), consider:
- Extracting padding values to CSS variables or theme configuration
- Creating reusable label classes for consistent info row styling
- Implementing a theme manager to swap QSS files dynamically

### Responsive Design
For future enhancements supporting mobile or tablet interfaces:
- Consider scaling padding values based on screen DPI
- Implement breakpoints for different screen sizes
- Use percentage-based or em-based spacing instead of fixed pixels

### Accessibility
Current design maintains good contrast ratios. Future improvements:
- Ensure adequate line height for users with visual impairments
- Support user-configurable spacing preferences
- Add ARIA labels or Qt accessibility properties for screen readers

## References

- **PyQt6 QSS Documentation**: Styling syntax and property reference
- **Qt Style Sheets Reference**: Selector specificity and inheritance rules
- **Material Design Guidelines**: Spacing and density recommendations (used for padding value selection)
- **Existing Codebase**:
  - `styles.qss`: Current styling definitions
  - `tabs/overview.py`: Overview tab implementation
  - `utils/sys_info.py`: System information gathering (unmodified)
