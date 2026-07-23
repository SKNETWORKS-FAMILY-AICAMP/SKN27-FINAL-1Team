import React, { useEffect, useMemo, useRef, useState } from "react";

import { useLocation, useNavigate } from "react-router-dom";

import "./RecipeList.css";

import imageRecommendation from "../../assets/extracted/images/image_recommendation.png";

import imageSearch from "../../assets/extracted/images/image_search.png";

import { useAppDialog } from "../../components/AppDialog.jsx";

import { API_URL } from "../../utils/api.js";

import {
  getStoredRecipeByRecipeId,
  readStoredRecipes,
  removeRecommendationResult,
  removeStoredRecipe,
  saveRecommendationResult,
  saveStoredRecipe,
} from "../../utils/savedRecipes.js";

import { RecipeFilterConfig } from "./recipeFilterConfig.js";
import { buildRecipeFilterOptions, mergeRecipePages } from "./recipeListState.js";

const PAGE_SIZE = 20;

/** 개별 기능 연결 시 true로 전환 */
const FEATURE_FLAGS = {
  categoryFilter: true,
  timeFilter: true,
  levelFilter: true,
  savedRecipes: true,
};

function ImageSlot({ src, alt = "", className = "" }) {
  return (
    <span
      className={`recipe-list-image-slot ${src ? "is-filled" : ""} ${className}`}
    >
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  );
}

function formatCookingTime(minutes) {
  if (minutes == null) {
    return "-";
  }

  return `${minutes}분`;
}

function hasActiveFilters(criteria) {
  return (
    Boolean(criteria.query) ||
    Boolean(criteria.ingredient) ||
    criteria.category !== RecipeFilterConfig.FILTER_ALL ||
    criteria.timeFilter !== RecipeFilterConfig.FILTER_ALL ||
    criteria.levelFilter !== RecipeFilterConfig.FILTER_ALL
  );
}

function RecipeList() {
  const location = useLocation();

  const navigate = useNavigate();

  const { dialogNode, showAlert } = useAppDialog();

  const criteria = useMemo(
    () => RecipeFilterConfig.parseSearchParams(location.search),

    [location.search],
  );

  const [draftSearchTerm, setDraftSearchTerm] = useState(criteria.query || criteria.ingredient);

  const [recipes, setRecipes] = useState([]);

  const [total, setTotal] = useState(0);

  const [page, setPage] = useState(1);

  const [hasNext, setHasNext] = useState(false);

  const [facets, setFacets] = useState(null);

  const [isLoading, setIsLoading] = useState(false);

  const [error, setError] = useState(null);

  const [retryVersion, setRetryVersion] = useState(0);

  const [isRecipeTypeMenuOpen, setIsRecipeTypeMenuOpen] = useState(false);

  const [savedIds, setSavedIds] = useState(() =>
    readStoredRecipes().map((recipe) => recipe.recipeId),
  );

  const [busyIds, setBusyIds] = useState(() => new Set());

  const loadMoreRef = useRef(null);

  const lastSearchRef = useRef(location.search);
  const fetchPage = lastSearchRef.current !== location.search ? 1 : page;

  const navigateToCriteria = (nextCriteria) => {
    const params = RecipeFilterConfig.buildSearchParams(nextCriteria);

    const search = params.toString();

    navigate(search ? `/recipes?${search}` : "/recipes", { replace: true });
  };

  useEffect(() => {
    setDraftSearchTerm(criteria.query || criteria.ingredient);

    setRecipes([]);

    setTotal(0);

    setPage(1);

    setHasNext(false);

    setFacets(null);

    setError(null);

    lastSearchRef.current = location.search;
  }, [location.search, criteria.query, criteria.ingredient]);

  useEffect(() => {
    const controller = new AbortController();

    const fetchRecipes = async () => {
      setIsLoading(true);

      setError(null);

      try {
        const params = new URLSearchParams(
          RecipeFilterConfig.toApiParams(criteria, fetchPage, PAGE_SIZE),
        );

        const response = await fetch(
          `${API_URL}/api/v1/recipes/search?${params}`,
          {
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          throw new Error("레시피 검색에 실패했습니다.");
        }

        const data = await response.json();

        setRecipes((prev) => mergeRecipePages(prev, data.items, fetchPage === 1));

        setTotal(data.total);

        setHasNext(data.has_next);

        if (fetchPage === 1) {
          setFacets(data.facets ?? null);
        }
      } catch (fetchError) {
        if (fetchError.name === "AbortError") {
          return;
        }

        setError(fetchError.message || "레시피 검색에 실패했습니다.");

        if (fetchPage === 1) {
          setRecipes([]);

          setTotal(0);

          setHasNext(false);
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    fetchRecipes();

    return () => controller.abort();
  }, [location.search, page, criteria, fetchPage, retryVersion]);

  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !hasNext || isLoading || error) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        observer.disconnect();
        setPage((current) => current + 1);
      },
      { rootMargin: "300px 0px" },
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [error, hasNext, isLoading, recipes.length]);

  const filterOptions = useMemo(
    () => buildRecipeFilterOptions(total, facets),
    [facets, total],
  );

  const recipeTypeOptions = filterOptions.recipeTypes;
  const cookingTimeOptions = filterOptions.cookingTimes;
  const difficultyOptions = filterOptions.difficulties;

  const hasActiveFilter =
    hasActiveFilters(criteria) || criteria.browseAll;

  const submitSearch = (event) => {
    event.preventDefault();

    const query = draftSearchTerm.trim();

    const hasFilters =
      criteria.category !== RecipeFilterConfig.FILTER_ALL ||
      criteria.timeFilter !== RecipeFilterConfig.FILTER_ALL ||
      criteria.levelFilter !== RecipeFilterConfig.FILTER_ALL;

    if (!query && !hasFilters) {
      navigateToCriteria({
        query: "",

        category: RecipeFilterConfig.FILTER_ALL,

        timeFilter: RecipeFilterConfig.FILTER_ALL,

        levelFilter: RecipeFilterConfig.FILTER_ALL,

        browseAll: true,
      });

      return;
    }

    navigateToCriteria({
      ...criteria,
      query,
      ingredient: "",
      browseAll: false,
    });
  };

  const handleFilterChange = (updates) => {
    navigateToCriteria({
      ...criteria,

      ...updates,

      browseAll: false,
    });
  };

  const isRecipeSaved = (recipeId) =>
    savedIds.some((id) => String(id) === String(recipeId));

  const toggleSaved = async (recipe) => {
    if (!FEATURE_FLAGS.savedRecipes) {
      return;
    }

    const recipeId = recipe?.recipe_id;
    if (recipeId == null || busyIds.has(recipeId)) {
      return;
    }

    const token = window.localStorage.getItem("bobbeori-token");
    if (!token) {
      await showAlert("레시피를 저장하려면 로그인이 필요해요.", {
        title: "로그인이 필요해요",
      });
      navigate("/login");
      return;
    }

    setBusyIds((prev) => new Set(prev).add(recipeId));
    try {
      if (isRecipeSaved(recipeId)) {
        const stored = getStoredRecipeByRecipeId(recipeId);
        if (stored?.recommendationId) {
          await removeRecommendationResult(stored.recommendationId);
        }
        if (stored?.storageId) {
          removeStoredRecipe(stored.storageId);
        }
        setSavedIds((prev) => prev.filter((id) => String(id) !== String(recipeId)));
        return;
      }

      const savedResult = await saveRecommendationResult(recipe, "manual_save");
      saveStoredRecipe({
        recipe_id: recipe.recipe_id,
        recommendation_id: savedResult.recommendation_id,
        title: recipe.title,
        category: recipe.category,
        image: recipe.main_image_url,
        source: "저장한 레시피",
        savedType: "saved",
      });
      setSavedIds((prev) => [...prev, recipeId]);
    } catch {
      // keep previous heart / local state
    } finally {
      setBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(recipeId);
        return next;
      });
    }
  };

  const resetFilters = () => {
    navigate("/recipes");
  };

  const showNoResults = !isLoading && !error && recipes.length === 0;

  const resultsTitle = criteria.query
    ? "검색 결과"
    : criteria.browseAll
      ? "전체 레시피"
      : hasActiveFilters(criteria)
        ? "필터 결과"
        : "전체 레시피";

  const resultsCount = total;

  return (
    <section className="recipe-list-page" aria-labelledby="recipe-list-title">
      <div className="recipe-list-hero">
        <div className="recipe-list-hero__copy">
          <h1 id="recipe-list-title">
            다양한 레시피를
            <strong>한곳에서 만나보세요</strong>
          </h1>

          <p>
            국, 볶음, 반찬, 파스타까지 오늘 끌리는 메뉴를 자유롭게 둘러보세요.
          </p>

          <form
            className="recipe-list-search"
            aria-label="레시피 검색"
            onSubmit={submitSearch}
          >
            <span aria-hidden="true" />

            <input
              type="search"
              placeholder="레시피 이름을 검색해보세요"
              value={draftSearchTerm}
              onChange={(event) => setDraftSearchTerm(event.target.value)}
            />

            <button type="submit">검색</button>
          </form>
        </div>

        <ImageSlot className="recipe-list-hero__image" src={imageSearch} />
      </div>

      <section className="recipe-list-filter" aria-label="레시피 조건 필터">
        <div className="recipe-list-filter__controls">
          <div className="recipe-list-choice-group recipe-list-choice-group--select">
            <span>요리타입</span>
            <div
              className="recipe-list-type-dropdown"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) {
                  setIsRecipeTypeMenuOpen(false);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape") setIsRecipeTypeMenuOpen(false);
              }}
            >
              <button
                className="recipe-list-type-trigger"
                type="button"
                aria-haspopup="menu"
                aria-expanded={isRecipeTypeMenuOpen}
                disabled={!FEATURE_FLAGS.categoryFilter}
                onClick={() => setIsRecipeTypeMenuOpen((isOpen) => !isOpen)}
              >
                <span>{recipeTypeOptions.find((option) => option.value === criteria.category)?.label}</span>
                <span className="recipe-list-type-trigger__arrow" aria-hidden="true" />
              </button>

              {isRecipeTypeMenuOpen ? (
                <div className="recipe-list-type-menu" role="menu">
                  {recipeTypeOptions.map((option) => (
                    <button
                      className={criteria.category === option.value ? "is-active" : ""}
                      key={option.value}
                      type="button"
                      role="menuitemradio"
                      aria-checked={criteria.category === option.value}
                      onClick={() => {
                        handleFilterChange({ category: option.value });
                        setIsRecipeTypeMenuOpen(false);
                      }}
                    >
                      <span>{option.label}</span>
                      {criteria.category === option.value ? <span aria-hidden="true">✓</span> : null}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

          <div className="recipe-list-choice-group" role="group" aria-label="조리시간">
            <span>조리시간</span>
            <div className="recipe-list-choice-group__options">
              {cookingTimeOptions.map((option) => (
                <button
                  className={criteria.timeFilter === option.value ? "is-active" : ""}
                  key={option.value}
                  type="button"
                  aria-pressed={criteria.timeFilter === option.value}
                  disabled={!FEATURE_FLAGS.timeFilter}
                  onClick={() => handleFilterChange({ timeFilter: option.value })}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="recipe-list-choice-group" role="group" aria-label="난이도">
            <span>난이도</span>
            <div className="recipe-list-choice-group__options">
              {difficultyOptions.map((option) => (
                <button
                  className={criteria.levelFilter === option ? "is-active" : ""}
                  key={option}
                  type="button"
                  aria-pressed={criteria.levelFilter === option}
                  disabled={!FEATURE_FLAGS.levelFilter}
                  onClick={() => handleFilterChange({ levelFilter: option })}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>

        </div>
      </section>

      <section
        className="recipe-list-results"
        aria-labelledby="recipe-results-title"
      >
        <h2 id="recipe-results-title">
          {resultsTitle} <span>({resultsCount})</span>
          {hasActiveFilter ? (
            <button
              className="recipe-list-reset"
              type="button"
              onClick={resetFilters}
            >
              필터 초기화
            </button>
          ) : null}
        </h2>

        {error ? (
          <div
            className="recipe-list-status recipe-list-status--error"
            role="alert"
          >
            <span>{error}</span>
            <button
              type="button"
              onClick={() => {
                setIsLoading(true);
                setError(null);
                setRetryVersion((current) => current + 1);
              }}
            >
              다시 시도
            </button>
          </div>
        ) : null}

        {isLoading && page === 1 ? (
          <p className="recipe-list-status" aria-live="polite">
            레시피를 검색하고 있어요...
          </p>
        ) : null}

        <div className="recipe-list-grid">
          {!error
            ? recipes.map((recipe) => (
                <article
                  className="recipe-card"
                  key={recipe.recipe_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/recipes/${recipe.recipe_id}`)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();

                      navigate(`/recipes/${recipe.recipe_id}`);
                    }
                  }}
                >
                  <div className="recipe-card__media">
                    <button
                      type="button"
                      className="recipe-card__save"
                      aria-label={`${recipe.title} 저장`}
                      aria-pressed={isRecipeSaved(recipe.recipe_id)}
                      disabled={!FEATURE_FLAGS.savedRecipes || busyIds.has(recipe.recipe_id)}
                      title={
                        FEATURE_FLAGS.savedRecipes
                          ? undefined
                          : "준비 중인 기능입니다"
                      }
                      onClick={(event) => {
                        event.stopPropagation();

                        toggleSaved(recipe);
                      }}
                    >
                      {isRecipeSaved(recipe.recipe_id) ? "♥" : "♡"}
                    </button>

                    <ImageSlot
                      className="recipe-card__image"
                      src={recipe.main_image_url}
                      alt=""
                    />
                  </div>

                  <div className="recipe-card__body">
                    <h3>{recipe.title}</h3>

                    <p>
                      {formatCookingTime(recipe.cooking_time_min)} ·{" "}
                      {recipe.difficulty || "-"}
                    </p>

                    {recipe.category ? (
                      <div>
                        <span>{recipe.category}</span>
                      </div>
                    ) : null}
                  </div>
                </article>
              ))
            : null}

          {showNoResults ? (
            <article className="recipe-card recipe-card--empty">
              <div className="recipe-card__body">
                <h3>조건에 맞는 레시피가 없어요.</h3>

                <p>검색어를 바꾸거나 필터를 초기화해보세요.</p>
              </div>
            </article>
          ) : null}
        </div>

        <div
          className="recipe-list-load-more"
          ref={loadMoreRef}
          aria-live="polite"
        >
          {!error && isLoading && page > 1 ? "레시피를 더 불러오는 중..." : null}
          {!error && !isLoading && !hasNext && recipes.length > 0
            ? "모든 레시피를 보고 있어요"
            : null}
        </div>
      </section>

      <ImageSlot className="recipe-list-mobile-art" src={imageRecommendation} />
      {dialogNode}
    </section>
  );
}

export default RecipeList;
