import { useTranslation } from 'react-i18next';
import './LanguageToggle.css';

const LanguageToggle = () => {
  const { i18n, t } = useTranslation();

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'ko' : 'en';
    i18n.changeLanguage(newLang);
  };

  const getCurrentLanguageLabel = () => {
    return i18n.language === 'en' ? 'EN' : '한';
  };

  const getNextLanguageLabel = () => {
    return i18n.language === 'en' ? '한국어' : 'English';
  };

  return (
    <div className="language-toggle">
      <button 
        onClick={toggleLanguage}
        className="language-toggle-btn"
        title={`${t('language.selector')}: ${getNextLanguageLabel()}`}
        aria-label={`Switch to ${getNextLanguageLabel()}`}
      >
        <span className="current-lang">{getCurrentLanguageLabel()}</span>
        <span className="toggle-icon">🌐</span>
      </button>
    </div>
  );
};

export default LanguageToggle;
