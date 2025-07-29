# Language Toggle Feature Demo

## Overview
The Bedrock Shopping Assistant now supports both English and Korean languages with a seamless toggle feature.

## Features Added

### 1. **Language Toggle Component**
- Located in the top-right corner of both Chat and Monitoring views
- Shows current language (EN/한) with a globe icon
- Smooth hover animations and transitions
- Accessible with proper ARIA labels

### 2. **Internationalization (i18n) Support**
- Uses `react-i18next` for robust translation management
- Automatic language detection from browser/localStorage
- Fallback to English if translation missing

### 3. **Comprehensive Translations**
- **English**: Complete UI text coverage
- **Korean**: Full Korean translations for all interface elements
- Organized translation keys for easy maintenance

### 4. **Updated Components**
- ✅ **ChatBox**: Title, placeholders, buttons, status messages
- ✅ **UserSelector**: Profile labels and user information
- ✅ **RecommendationBubbles**: Recommendation titles and actions
- ✅ **MonitoringDashboard**: Navigation and monitoring labels
- ✅ **LanguageToggle**: Standalone toggle component

## How to Use

### For Users:
1. Click the language toggle button (🌐) in the top-right corner
2. Interface instantly switches between English ↔ Korean
3. Language preference is saved in browser localStorage

### For Developers:
```typescript
import { useTranslation } from 'react-i18next';

const MyComponent = () => {
  const { t } = useTranslation();
  
  return (
    <div>
      <h1>{t('chat.title')}</h1>
      <p>{t('chat.subtitle')}</p>
    </div>
  );
};
```

## Translation Structure

```
src/i18n/
├── index.ts              # i18n configuration
└── locales/
    ├── en.json          # English translations
    └── ko.json          # Korean translations
```

## Key Translation Categories

- **common**: Loading, error, action buttons
- **navigation**: Menu items, view names
- **chat**: Chat interface, messages, status
- **user**: User profiles and selection
- **products**: Product information and actions
- **monitoring**: System monitoring interface
- **language**: Language selector labels

## Technical Implementation

### Dependencies Added:
```json
{
  "react-i18next": "^13.x.x",
  "i18next": "^23.x.x",
  "i18next-browser-languagedetector": "^7.x.x"
}
```

### Key Features:
- **Language Detection**: Automatically detects user's preferred language
- **Persistent Storage**: Remembers language choice across sessions
- **Responsive Design**: Toggle works on all screen sizes
- **Accessibility**: Full ARIA support and keyboard navigation
- **Performance**: Lazy loading of translation resources

## Testing the Feature

1. **Start the development server**:
   ```bash
   cd frontend && npm run dev
   ```

2. **Test language switching**:
   - Click the language toggle in the top-right corner
   - Verify all text changes to Korean/English
   - Check that preference persists on page reload

3. **Test different components**:
   - Navigate between Chat and Monitoring views
   - Verify translations work in all sections
   - Test user selector and recommendation bubbles

## Future Enhancements

- Add more languages (Japanese, Chinese, Spanish)
- Implement RTL language support
- Add date/time localization
- Include number and currency formatting
- Voice interface language switching

## Troubleshooting

### Common Issues:
1. **Missing translations**: Check console for missing translation keys
2. **Language not persisting**: Verify localStorage is enabled
3. **Build errors**: Ensure all translation files are valid JSON

### Debug Mode:
Enable debug mode in `src/i18n/index.ts`:
```typescript
i18n.init({
  debug: true, // Enable for development
  // ... other config
});
```

This will log translation loading and missing keys to the console.
