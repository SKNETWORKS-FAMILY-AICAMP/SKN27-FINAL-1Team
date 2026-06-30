import React, { useEffect, useMemo, useRef, useState } from "react";

import { useLocation, useNavigate } from "react-router-dom";

import "./RecipeList.css";

import imageRecommendation from "../../assets/extracted/images/image_recommendation.png";

import imageSearch from "../../assets/extracted/images/image_search.png";

import { recipeQuickMenus } from "../../mock/recipeListMock.js";

import { RecipeFilterConfig } from "./recipeFilterConfig.js";

const PAGE_SIZE = 20;

const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";

const recipeTypeOptions = RecipeFilterConfig.toSelectOptions(
  RecipeFilterConfig.recipeTypes,
  `${RecipeFilterConfig.labels.recipeType}`,
);

const cookingTimeOptions = RecipeFilterConfig.toSelectOptions(
  RecipeFilterConfig.cookingTimes,
  `${RecipeFilterConfig.labels.cookingTime}`,
);

const difficultyOptions = RecipeFilterConfig.toSelectOptions(
  RecipeFilterConfig.difficulties,
  `${RecipeFilterConfig.labels.difficulty}`,
);

/** 개별 기능 연결 시 true로 전환 */
const FEATURE_FLAGS = {
  quickMenu: false,
  categoryFilter: true,
  timeFilter: true,
  levelFilter: true,
  sortFilter: false,
  savedRecipes: false,
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

function GridIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" focusable="false">
      <rect x="3" y="3" width="5" height="5" rx="1.2" />
      <rect x="12" y="3" width="5" height="5" rx="1.2" />
      <rect x="3" y="12" width="5" height="5" rx="1.2" />
      <rect x="12" y="12" width="5" height="5" rx="1.2" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" focusable="false">
      <rect x="3" y="4" width="3" height="3" rx="0.8" />
      <rect x="8" y="4.5" width="9" height="2" rx="1" />
      <rect x="3" y="8.5" width="3" height="3" rx="0.8" />
      <rect x="8" y="9" width="9" height="2" rx="1" />
      <rect x="3" y="13" width="3" height="3" rx="0.8" />
      <rect x="8" y="13.5" width="9" height="2" rx="1" />
    </svg>
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

  const criteria = useMemo(
    () => RecipeFilterConfig.parseSearchParams(location.search),

    [location.search],
  );

  const [draftSearchTerm, setDraftSearchTerm] = useState(criteria.query || criteria.ingredient);

  const [recipes, setRecipes] = useState([]);

  const [total, setTotal] = useState(0);

  const [page, setPage] = useState(1);

  const [hasNext, setHasNext] = useState(false);

  const [isLoading, setIsLoading] = useState(false);

  const [error, setError] = useState(null);

  const [viewMode, setViewMode] = useState("grid");

  const [sortBy, setSortBy] = useState(RecipeFilterConfig.sortOptions[0].value);

  const [showSavedOnly, setShowSavedOnly] = useState(false);

  const [savedIds, setSavedIds] = useState([]);

  const lastSearchRef = useRef(location.search);
  const fetchPage = lastSearchRef.current !== location.search ? 1 : page;

  const navigateToCriteria = (nextCriteria) => {
    const params = RecipeFilterConfig.buildSearchParams(nextCriteria);

    const search = params.toString();

    navigate(search ? `/recipes?${search}` : "/recipes", { replace: true });
  };

  useEffect(() => {
    setDraftSearchTerm(criteria.query || criteria.ingredient);

    setPage(1);

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
          `${apiUrl}/api/v1/recipes/search?${params}`,
          {
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          throw new Error("레시피 검색에 실패했습니다.");
        }

        const data = await response.json();

        setRecipes((prev) =>
          fetchPage === 1 ? data.items : [...prev, ...data.items],
        );

        setTotal(data.total);

        setHasNext(data.has_next);
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
  }, [location.search, page, criteria, fetchPage]);

  const hasActiveFilter =
    hasActiveFilters(criteria) || criteria.browseAll || showSavedOnly;

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

  const handleQuickMenu = (title) => {
    if (!FEATURE_FLAGS.quickMenu) {
      return;
    }

    setShowSavedOnly(false);
    setSortBy(RecipeFilterConfig.sortOptions[0].value);

    if (title === "인기 레시피") {
      setSortBy("인기순");
      navigate("/recipes");
      return;
    }

    if (title === "간단 레시피") {
      navigateToCriteria({
        query: "",
        category: RecipeFilterConfig.FILTER_ALL,
        timeFilter: "15분이내",
        levelFilter: "초급",
        browseAll: false,
      });
      return;
    }

    if (title === "요리 입문") {
      navigateToCriteria({
        query: "",
        category: RecipeFilterConfig.FILTER_ALL,
        timeFilter: RecipeFilterConfig.FILTER_ALL,
        levelFilter: "초급",
        browseAll: false,
      });
      return;
    }

    if (title === "저장한 레시피") {
      setShowSavedOnly(true);
      navigate("/recipes");
    }
  };

  const toggleSaved = (recipeId) => {
    if (!FEATURE_FLAGS.savedRecipes) {
      return;
    }

    setSavedIds((prev) =>
      prev.includes(recipeId)
        ? prev.filter((id) => id !== recipeId)
        : [...prev, recipeId],
    );
  };

  const resetFilters = () => {
    setShowSavedOnly(false);

    setSortBy(RecipeFilterConfig.sortOptions[0].value);

    navigate("/recipes");
  };

  const showNoResults = !isLoading && !error && recipes.length === 0;

  const resultsTitle = showSavedOnly
    ? "저장한 레시피"
    : criteria.query
      ? "검색 결과"
      : criteria.browseAll
        ? "전체 레시피"
        : hasActiveFilters(criteria)
          ? "필터 결과"
          : "전체 레시피";

  const resultsCount = total;

  const isFilterSectionPending =
    !FEATURE_FLAGS.categoryFilter &&
    !FEATURE_FLAGS.timeFilter &&
    !FEATURE_FLAGS.levelFilter &&
    !FEATURE_FLAGS.sortFilter;

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
              placeholder="레시피명, 재료명을 검색해보세요"
              value={draftSearchTerm}
              onChange={(event) => setDraftSearchTerm(event.target.value)}
            />

            <button type="submit">검색</button>
          </form>
        </div>

        <ImageSlot className="recipe-list-hero__image" src={imageSearch} />
      </div>

      <div
        className={`recipe-list-quick${FEATURE_FLAGS.quickMenu ? "" : " is-pending"}`}
        aria-label="레시피 바로가기"
        aria-disabled={!FEATURE_FLAGS.quickMenu}
      >
        {recipeQuickMenus.map((menu) => (
          <button
            className="recipe-list-quick-card"
            type="button"
            key={menu.title}
            disabled={!FEATURE_FLAGS.quickMenu}
            title={
              FEATURE_FLAGS.quickMenu ? menu.title : "준비 중인 기능입니다"
            }
            onClick={() => handleQuickMenu(menu.title)}
          >
            <ImageSlot
              className={`recipe-list-quick-card__icon is-${menu.mark || "image"}`}
              src={menu.image}
            />

            <span>
              <strong>{menu.title}</strong>

              <small>{menu.description}</small>
            </span>
          </button>
        ))}
      </div>

      <section
        className={`recipe-list-filter${isFilterSectionPending ? " is-pending" : ""}`}
        aria-labelledby="recipe-filter-title"
      >
        <h2 id="recipe-filter-title">
          레시피 필터
          {!FEATURE_FLAGS.sortFilter ? (
            <span className="recipe-list-pending-label">정렬 준비 중</span>
          ) : null}
        </h2>

        <div className="recipe-list-filter__controls">
          <select
            aria-label={RecipeFilterConfig.labels.recipeType}
            value={criteria.category}
            disabled={!FEATURE_FLAGS.categoryFilter}
            title={
              FEATURE_FLAGS.categoryFilter ? undefined : "준비 중인 기능입니다"
            }
            onChange={(event) =>
              handleFilterChange({ category: event.target.value })
            }
          >
            {recipeTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select
            aria-label={RecipeFilterConfig.labels.cookingTime}
            value={criteria.timeFilter}
            disabled={!FEATURE_FLAGS.timeFilter}
            title={
              FEATURE_FLAGS.timeFilter ? undefined : "준비 중인 기능입니다"
            }
            onChange={(event) =>
              handleFilterChange({ timeFilter: event.target.value })
            }
          >
            {cookingTimeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select
            aria-label={RecipeFilterConfig.labels.difficulty}
            value={criteria.levelFilter}
            disabled={!FEATURE_FLAGS.levelFilter}
            title={
              FEATURE_FLAGS.levelFilter ? undefined : "준비 중인 기능입니다"
            }
            onChange={(event) =>
              handleFilterChange({ levelFilter: event.target.value })
            }
          >
            {difficultyOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <div className="recipe-list-filter__right">
            <select
              aria-label={RecipeFilterConfig.labels.sort}
              value={sortBy}
              disabled={!FEATURE_FLAGS.sortFilter}
              title={
                FEATURE_FLAGS.sortFilter ? undefined : "준비 중인 기능입니다"
              }
              onChange={(event) => setSortBy(event.target.value)}
            >
              {RecipeFilterConfig.sortOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <div className="recipe-list-view" aria-label="보기 방식">
              <button
                className={viewMode === "grid" ? "is-active" : ""}
                type="button"
                aria-label="그리드 보기"
                title="그리드 보기"
                onClick={() => setViewMode("grid")}
              >
                <GridIcon />
              </button>

              <button
                className={viewMode === "list" ? "is-active" : ""}
                type="button"
                aria-label="리스트 보기"
                title="리스트 보기"
                onClick={() => setViewMode("list")}
              >
                <ListIcon />
              </button>
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
          <p
            className="recipe-list-status recipe-list-status--error"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {isLoading && page === 1 ? (
          <p className="recipe-list-status" aria-live="polite">
            레시피를 검색하고 있어요...
          </p>
        ) : null}

        <div
          className={
            viewMode === "list"
              ? "recipe-list-grid is-list"
              : "recipe-list-grid"
          }
        >
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
                      aria-pressed={savedIds.includes(recipe.recipe_id)}
                      disabled={!FEATURE_FLAGS.savedRecipes}
                      title={
                        FEATURE_FLAGS.savedRecipes
                          ? undefined
                          : "준비 중인 기능입니다"
                      }
                      onClick={(event) => {
                        event.stopPropagation();

                        toggleSaved(recipe.recipe_id);
                      }}
                    >
                      {savedIds.includes(recipe.recipe_id) ? "♥" : "♡"}
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

        {!error ? (
          <button
            className="recipe-list-more"
            type="button"
            disabled={!hasNext || isLoading}
            onClick={() => setPage((prev) => prev + 1)}
          >
            {!hasNext
              ? "모든 레시피를 보고 있어요"
              : isLoading
                ? "불러오는 중..."
                : "더 많은 레시피 보기"}
          </button>
        ) : null}
      </section>

      <ImageSlot className="recipe-list-mobile-art" src={imageRecommendation} />
    </section>
  );
}

export default RecipeList;
