import React, { useState } from 'react';
import { API_URL } from '../utils/api.js';
import './OnboardingModal.css';

const ALLERGY_OPTIONS = ['땅콩', '우유', '계란', '밀', '갑각류', '대두', '견과류', '생선'];
const DISLIKE_OPTIONS = ['오이', '가지', '당근', '피망', '브로콜리', '버섯', '연근', '셀러리'];
const PREFERRED_OPTIONS = ['돼지고기', '소고기', '닭고기', '양파', '마늘', '대파', '버섯', '청양고추', '치즈', '두부'];

export default function OnboardingModal({ seenKey = 'hasSeenOnboarding_v4', onClose }) {
  const [step, setStep] = useState(1);
  const [allergies, setAllergies] = useState([]);
  const [dislikes, setDislikes] = useState([]);
  const [preferred, setPreferred] = useState([]);
  const [customAllergy, setCustomAllergy] = useState('');
  const [customAllergyTags, setCustomAllergyTags] = useState([]);
  const [customDislike, setCustomDislike] = useState('');
  const [customDislikeTags, setCustomDislikeTags] = useState([]);
  const [customPreferred, setCustomPreferred] = useState('');
  const [customPreferredTags, setCustomPreferredTags] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleSelection = (list, setList, item) => {
    if (list.includes(item)) {
      setList(list.filter(i => i !== item));
    } else {
      setList([...list, item]);
    }
  };

  // 직접 입력값을 스페이스/엔터 기준 태그로 추가합니다.
  const addTag = (tags, setTags, value, setValue) => {
    const nextValue = value.trim();
    if (!nextValue || tags.includes(nextValue)) return;
    setTags([...tags, nextValue]);
    setValue('');
  };

  // 입력창이 비어 있을 때 Backspace를 누르면 마지막 태그를 지웁니다.
  const handleTagKeyDown = (event, tags, setTags, value, setValue) => {
    if ((event.key === ' ' || event.key === 'Enter') && value.trim()) {
      event.preventDefault();
      addTag(tags, setTags, value, setValue);
      return;
    }

    if (event.key === 'Backspace' && !value && tags.length > 0) {
      event.preventDefault();
      setTags(tags.slice(0, -1));
    }
  };

  // 온보딩 3단계에서 같은 태그 입력 UI를 재사용합니다.
  const renderTagInput = ({ tags, setTags, value, setValue, placeholder }) => (
    <div className="tag-input" onClick={(event) => event.currentTarget.querySelector('input')?.focus()}>
      {tags.map((item) => (
        <span className="tag-input__chip" key={item}>
          {item}
          <button type="button" onClick={() => setTags(tags.filter((tag) => tag !== item))} aria-label={`${item} 삭제`}>×</button>
        </span>
      ))}
      <input
        type="text"
        placeholder={tags.length ? '' : placeholder}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => handleTagKeyDown(event, tags, setTags, value, setValue)}
        onBlur={() => addTag(tags, setTags, value, setValue)}
      />
    </div>
  );

  const handleNext = () => {
    if (step < 3) setStep(step + 1);
    else handleSubmit();
  };

  const handlePrev = () => {
    if (step > 1) setStep(step - 1);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    
    const finalAllergies = [...allergies, ...customAllergyTags];
    if (customAllergy.trim() && !finalAllergies.includes(customAllergy.trim())) {
      finalAllergies.push(customAllergy.trim());
    }
    
    const finalDislikes = [...dislikes, ...customDislikeTags];
    if (customDislike.trim() && !finalDislikes.includes(customDislike.trim())) {
      finalDislikes.push(customDislike.trim());
    }

    const finalPreferred = [...preferred, ...customPreferredTags];
    if (customPreferred.trim() && !finalPreferred.includes(customPreferred.trim())) {
      finalPreferred.push(customPreferred.trim());
    }

    const payload = {
      allergy: finalAllergies,
      disliked_ingredients: finalDislikes,
      preferred_ingredients: finalPreferred
    };

    try {
      const token = localStorage.getItem('bobbeori-token');
      
      const res = await fetch(`${API_URL}/api/v1/onboarding`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        console.warn('API POST failed, but continuing for UI completion.');
      }
      
      localStorage.setItem('bobbeori-onboarding-settings', JSON.stringify(payload));
      localStorage.setItem(seenKey, 'true');
      onClose();
    } catch (err) {
      console.error('온보딩 저장 중 오류:', err);
      localStorage.setItem('bobbeori-onboarding-settings', JSON.stringify(payload));
      localStorage.setItem(seenKey, 'true');
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-modal">
        <div className="onboarding-progress">
          {[1, 2, 3].map(s => (
            <div key={s} className={`progress-dot ${step >= s ? 'active' : ''}`}></div>
          ))}
        </div>

        <div className="onboarding-content">
          {step === 1 && (
            <div className="onboarding-step fade-in">
              <div className="onboarding-title">혹시 알레르기가 있으신가요?</div>
              <div className="onboarding-subtitle">안전한 레시피 추천을 위해 꼭 필요해요.</div>
              
              <div className="chip-group">
                {ALLERGY_OPTIONS.map((item) => (
                  <button 
                    key={item} 
                    className={`chip ${allergies.includes(item) ? 'selected' : ''}`}
                    onClick={() => toggleSelection(allergies, setAllergies, item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              {renderTagInput({
                tags: customAllergyTags,
                setTags: setCustomAllergyTags,
                value: customAllergy,
                setValue: setCustomAllergy,
                placeholder: '기타 알레르기가 있다면 적어주세요',
              })}
            </div>
          )}

          {step === 2 && (
            <div className="onboarding-step fade-in">
              <div className="onboarding-title">피하고 싶은 식재료가 있나요?</div>
              <div className="onboarding-subtitle">여러 개를 자유롭게 선택해주세요.</div>
              
              <div className="chip-group">
                {DISLIKE_OPTIONS.map((item) => (
                  <button 
                    key={item} 
                    className={`chip ${dislikes.includes(item) ? 'selected' : ''}`}
                    onClick={() => toggleSelection(dislikes, setDislikes, item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              {renderTagInput({
                tags: customDislikeTags,
                setTags: setCustomDislikeTags,
                value: customDislike,
                setValue: setCustomDislike,
                placeholder: '기타 싫어하는 식재료를 적어주세요',
              })}
            </div>
          )}

          {step === 3 && (
            <div className="onboarding-step fade-in">
              <div className="onboarding-title">자주 찾는 선호 식재료가 있나요?</div>
              <div className="onboarding-subtitle">취향에 꼭 맞는 레시피를 추천해 드릴게요.</div>
              
              <div className="chip-group">
                {PREFERRED_OPTIONS.map((item) => (
                  <button 
                    key={item} 
                    className={`chip ${preferred.includes(item) ? 'selected' : ''}`}
                    onClick={() => toggleSelection(preferred, setPreferred, item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              {renderTagInput({
                tags: customPreferredTags,
                setTags: setCustomPreferredTags,
                value: customPreferred,
                setValue: setCustomPreferred,
                placeholder: '기타 선호하는 식재료를 적어주세요',
              })}
            </div>
          )}

        </div>

        <div className="onboarding-footer">
          <button className="btn-later" onClick={() => {
            localStorage.setItem(seenKey, 'true');
            onClose();
          }}>다음에 설정하기</button>
          {step > 1 && (
            <button className="btn-prev" onClick={handlePrev}>이전</button>
          )}
          <button 
            className="btn-next" 
            onClick={handleNext}
            disabled={isSubmitting}
          >
            {step === 3 ? (isSubmitting ? '저장 중...' : '밥벌이 시작하기') : '다음'}
          </button>
        </div>
      </div>
    </div>
  );
}
