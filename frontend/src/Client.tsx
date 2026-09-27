import React,{useEffect,useMemo,useRef,useState} from 'react';
import {
  Language,
  SUPPORTED_LANGUAGES,
  createTranslator,
  getStoredLanguage,
  setStoredLanguage,
  applyLanguageDirection,
} from './i18n';
import PhoneInput, {
  isPhoneValid
} from './PhoneInput';
import QRCode from 'qrcode';
import Specialists from './Specialists';
import { BooklyAlertModal, BooklyConfirmModal } from './modals';
import {
  API,
  BOT_USERNAME,
  tg,
  confirmAsync,
  initData,
  getClientTimeZone,
  getClientLocalDateKey,
  getDateKeyForTimeZone,
  formatUtcForTimeZone,
  headers,
  LOCALE_MAP,
  getLocale,
  money,
  localizedDays,
  TIMEZONE_OPTIONS,
  ALL_TIMEZONES,
  getTimeZoneLabel,
  getTimeZoneOffsetMinutes,
  formatGMTOffset,
  TIMEZONE_BY_OFFSET
} from './shared';
import { MyBookings } from './MyBookings';

export function Client({
  slug,
  onBack,
  t
}: {
  slug: string;
  onBack: () => void;
  t: (key: string, fallback?: string) => string;
}) {
  const [business, setBusiness] =
    useState<any>(null);

  const [services, setServices] =
    useState<any[]>([]);

  const [businessId, setBusinessId] =
  useState<number | null>(null);

  const [selected, setSelected] =
    useState<any>(null);

  const [specialists, setSpecialists] =
    useState<any[]>([]);

  const [selectedSpecialist, setSelectedSpecialist] =
    useState<any>(null);

  const clientTimeZone = getClientTimeZone();

  const [day, setDay] = useState(getClientLocalDateKey());

  const [slots, setSlots] =
    useState<string[]>([]);

  const [slotItems, setSlotItems] =
    useState<Array<{
      time: string;
      available: boolean;
    }>>([]);

  const [selectedTime, setSelectedTime] =
    useState('');

  const [slotsLoading, setSlotsLoading] =
    useState(false);

  const [clientName, setClientName] =
    useState(
      tg()?.initDataUnsafe?.user
        ?.first_name || ''
    );

  const [phone, setPhone] =
    useState('');

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState('');

  const [bookingLoading, setBookingLoading] =
    useState(false);

  const [isSaved, setIsSaved] =
    useState(false);

  const [savingBusiness, setSavingBusiness] =
    useState(false);

  const [savedBusinesses, setSavedBusinesses] =
    useState<any[]>([]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError('');

      try {
        if (!slug) {
          throw new Error(
            t('client.slugError')
          );
        }

        const response = await fetch(
          API +
            `/businesses/${encodeURIComponent(slug)}`
        );

        const text =
          await response.text();

        let data: any = null;

        try {
          data = text
            ? JSON.parse(text)
            : null;
        } catch {
          data = null;
        }

        if (!response.ok) {
          if (response.status === 403) {
            throw new Error(
              t('client.businessInactive')
            );
          }

          if (response.status === 404) {
            throw new Error(
              t('client.businessNotFound')
            );
          }

          throw new Error(
            data?.detail ||
            data?.message ||
            `${t('client.serverError')} ${response.status}`
          );
        }

        if (!data?.business) {
          throw new Error(
            t('client.businessDataError')
          );
        }

        if (!cancelled) {
          setBusiness(
            data.business
          );

          setServices(
            data.services || []
          );

          try {
            const specialistsResponse = await fetch(
              API + `/businesses/${data.business.id}/specialists`
            );
            if (specialistsResponse.ok) {
              const specialistsData = await specialistsResponse.json();
              setSpecialists(Array.isArray(specialistsData) ? specialistsData.filter((item: any) => item?.active !== false) : []);
            } else {
              setSpecialists([]);
            }
          } catch (specialistsError) {
            console.error('CLIENT SPECIALISTS LOAD ERROR:', specialistsError);
            setSpecialists([]);
          }
        }
      } catch (e: any) {
        console.error(
          'CLIENT LOAD ERROR:',
          e
        );

        if (!cancelled) {
          setBusiness(null);
          setServices([]);
          setError(
            e?.message ||
            t('client.businessLoadError')
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [slug, t]);

  useEffect(() => {
    const loadSaved = async () => {
      if (
        !initData() ||
        !business
      ) {
        return;
      }

      try {
        const response =
          await fetch(
            API +
              '/my/saved-businesses',
            {
              headers: headers()
            }
          );

        if (!response.ok) {
          return;
        }

        const data =
          await response.json();

        const list =
          Array.isArray(data)
            ? data
            : [];

        setSavedBusinesses(list);

        setIsSaved(
          list.some(
            (item: any) =>
              item.id === business.id
          )
        );
      } catch {
        setSavedBusinesses([]);
      }
    };

    loadSaved();
  }, [business]);

  const toggleSave = async () => {
    if (!business) {
      return;
    }

    if (!initData()) {
      alert(
        t('client.saveLoginRequired')
      );
      return;
    }

    setSavingBusiness(true);

    try {
      const response =
        await fetch(
          API +
            `/my/saved-businesses/${business.id}`,
          {
            method:
              isSaved
                ? 'DELETE'
                : 'POST',
            headers: headers()
          }
        );

      const data =
        await response
          .json()
          .catch(() => null);

      if (!response.ok) {
        throw new Error(
          data?.detail ||
          t('client.saveBusinessError')
        );
      }

      setIsSaved(!isSaved);
    } catch (e: any) {
      alert(
        e?.message ||
        t('client.saveBusinessError')
      );
    } finally {
      setSavingBusiness(false);
    }
  };

  const loadSlots = async (
    service: any,
    selectedDay: string,
    specialist: any = selectedSpecialist
  ) => {
    if (!business) {
      return;
    }

    setSlots([]);
    setSlotItems([]);
    setSelectedTime('');
    setSlotsLoading(true);

    try {
      const response =
        await fetch(
          API +
            `/businesses/${business.id}/availability?service_id=${service.id}&day=${selectedDay}&time_zone=${encodeURIComponent(clientTimeZone)}${specialist?.id ? `&specialist_id=${specialist.id}` : ''}`
        );

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail ||
          t('client.availabilityError')
        );
      }

      const nextSlots =
        Array.isArray(data?.slots)
          ? data.slots
          : [];

      setSlots(nextSlots);
      setSlotItems(
        Array.isArray(data?.slot_items)
          ? data.slot_items
          : nextSlots.map(
              (time: string) => ({
                time,
                available: true
              })
            )
      );
    } catch (e) {
      console.error(
        'AVAILABILITY ERROR:',
        e
      );

      setSlots([]);
      setSlotItems([]);
    } finally {
      setSlotsLoading(false);
    }
  };

  const findFirstAvailableDay = async (service: any, specialist: any = null) => {
    const startDate = new Date(`${day}T12:00:00`);
    const MAX_DAYS_TO_SEARCH = 90;
    for (let offset = 0; offset < MAX_DAYS_TO_SEARCH; offset += 1) {
      const candidate = new Date(startDate);
      candidate.setDate(startDate.getDate() + offset);
      const candidateDay = [
        candidate.getFullYear(),
        String(candidate.getMonth() + 1).padStart(2, '0'),
        String(candidate.getDate()).padStart(2, '0')
      ].join('-');
      const specialistQuery = specialist?.id ? `&specialist_id=${specialist.id}` : '';
      const response = await fetch(
        API +
          `/businesses/${business.id}/availability?service_id=${service.id}&day=${candidateDay}&time_zone=${encodeURIComponent(clientTimeZone)}${specialistQuery}`
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || t('client.availabilityError'));
      }
      const candidateSlots =
        Array.isArray(data?.slots)
          ? data.slots
          : [];

      const candidateSlotItems =
        Array.isArray(data?.slot_items)
          ? data.slot_items
          : candidateSlots.map(
              (time: string) => ({
                time,
                available: true
              })
            );

      if (candidateSlots.length > 0) {
        setDay(candidateDay);
        setSlots(candidateSlots);
        setSlotItems(candidateSlotItems);
        return true;
      }
    }
    setSlots([]);
    setSlotItems([]);
    return false;
  };

  const scrollToStep = (
    id: string,
    delay = 100
  ) => {
    window.setTimeout(() => {
      const element =
        document.getElementById(id);

      if (!element) {
        return;
      }

      const headerOffset = 74;
      const targetTop =
        element.getBoundingClientRect().top +
        window.scrollY -
        headerOffset;

      window.scrollTo({
        top: Math.max(0, targetTop),
        behavior: 'smooth'
      });
    }, delay);
  };

  const chooseService = async (service: any) => {
    if (!business) return;
    setSelected(service);
    setSelectedTime('');
    setSlots([]);
    setSlotItems([]);
    setError('');
    setSlotsLoading(true);
    try {
      await findFirstAvailableDay(service, selectedSpecialist);
    } catch (e) {
      console.error('SERVICE AVAILABILITY ERROR:', e);
      setSlots([]);
      setError(t('client.availabilityError'));
    } finally {
      setSlotsLoading(false);
      scrollToStep(
        'client-schedule-step',
        140
      );
    }
  };

  const chooseSpecialist = (specialist: any) => {
    setSelectedSpecialist(specialist);
    setSelected(null);
    setSelectedTime('');
    setSlots([]);
    setSlotItems([]);
    setDay(getClientLocalDateKey());
    setError('');
    scrollToStep(
      'client-services-step',
      140
    );
  };

  const chooseTime = (
    time: string
  ) => {
    setSelectedTime(time);

    setTimeout(() => {
      document
        .getElementById(
          'booking-form'
        )
        ?.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
    }, 50);
  };

  const submitBooking = async () => {
    if (
      !business ||
      !selected ||
      !selectedTime
    ) {
      return;
    }

    const name =
      clientName.trim();

    const clientPhone =
      phone.trim();

    if (!name) {
      alert(
        t('client.enterName')
      );
      return;
    }

    if (!clientPhone) {
      alert(
        t('client.enterPhone')
      );
      return;
    }

    if (!isPhoneValid(clientPhone)) {
  alert(
    t(
      'owner.invalidPhone',
      'Введите корректный номер телефона'
    )
  );
  return;
}

    setBookingLoading(true);

    try {
      const response =
        await fetch(
          API + '/bookings',
          {
            method: 'POST',
            headers: headers(),
            body: JSON.stringify({
              business_id:
                business.id,
              service_id:
                selected.id,
              specialist_id:
                selectedSpecialist?.id || null,
              client_name: name,
              client_phone:
                clientPhone,
              day,
              start:
                selectedTime,
              client_timezone: clientTimeZone
            })
          }
        );

      const data =
        await response.json();

      if (!response.ok) {
        alert(
          data?.detail ||
          t('client.bookingError')
        );
        return;
      }

                  alert(
        t('client.bookingSuccess')
      );

      setSelectedTime('');

      setTimeout(() => {
  const start = window.scrollY;
  const duration = 500;
  const startTime = performance.now();

  const animateScroll = (currentTime: number) => {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);

    const eased =
      1 - Math.pow(1 - progress, 3);

    window.scrollTo(
      0,
      Math.round(start * (1 - eased))
    );

    if (progress < 1) {
      requestAnimationFrame(animateScroll);
    }
  };

  requestAnimationFrame(animateScroll);
}, 100);

      await loadSlots(
        selected,
        day
      );
    } catch (e) {
      console.error(
        'BOOKING ERROR:',
        e
      );

      alert(
        t('client.bookingRetry')
      );
    } finally {
      setBookingLoading(false);
    }
  };

  const mapUrl =
    business &&
    business.latitude != null &&
    business.longitude != null
      ? `https://www.google.com/maps/search/?api=1&query=${business.latitude},${business.longitude}`
      : business?.address
        ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
            business.address
          )}`
        : '';

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="loading-logo">
          S
        </div>

        <h2>
          Skedwoo
        </h2>

        <div className="loading-spinner"></div>

        <p>
          {t('client.loadingBusiness')}
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <button
          className="back"
          onClick={onBack}
        >
          ← {t('common.back')}
        </button>

        <h2>
          {t('client.openError')}
        </h2>

        <p className="error">
          ❌ {error}
        </p>

        <button
          className="primary full"
          onClick={() =>
            window.location.reload()
          }
        >
          {t('client.retry')}
        </button>
      </div>
    );
  }

  if (!business) {
    return (
      <div className="card">
        <button
          className="back"
          onClick={onBack}
        >
          ← {t('common.back')}
        </button>

        <p>
          {t('client.businessNotFound')}
        </p>
      </div>
    );
  }

  return (
    <section className="client-booking-page">

      <button
        className="back"
        onClick={onBack}
      >
        ← {t('common.back')}
      </button>

      <div className="card client-business-overview">

  <div className="client-business-header">

    {business?.business_image && (
      <img
        src={business.business_image}
        alt={business.name}
        className="client-business-thumb"
        className="bookly-business-avatar"
      />
    )}

    <div className="client-business-header-info">
      <h1>
        {business.name}
      </h1>

      {business.description && (
        <p>
          {business.description}
        </p>
      )}
    
  </div>

</div>

<div className="client-contact-actions">

    {business.phone && (
      <div className="client-phone-row">
        <span className="client-phone-number">
          {business.phone}
        </span>

        <button
          type="button"
          className="client-copy-button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(
                business.phone
              );

              tg()?.showAlert?.(
                t(
                  'client.phoneCopied',
                  'Номер скопирован'
                )
              );
            } catch {
              const input =
                document.createElement('input');

              input.value = business.phone;
              document.body.appendChild(input);
              input.select();
              document.execCommand('copy');
              input.remove();

              tg()?.showAlert?.(
                t(
                  'client.phoneCopied',
                  'Номер скопирован'
                )
              );
            }
          }}
        >
          {t('client.copy', 'Скопировать')}
        </button>
      </div>
    )}

    {mapUrl && (
      <button
        type="button"
        className="client-contact-button"
        onClick={() => {
          if (tg()?.openLink) {
            tg().openLink(mapUrl);
          } else {
            window.open(
              mapUrl,
              '_blank'
            );
          }
        }}
      >
        <span className="client-contact-label">
          {business.address ||
            t('client.location')}
        </span>

        <span className="client-contact-arrow">
          →
        </span>
      </button>
    )}

    {business.instagram_url && (
      <button
        type="button"
        className="client-contact-button"
        onClick={() => {
          if (tg()?.openLink) {
            tg().openLink(business.instagram_url);
          } else {
            window.open(business.instagram_url, '_blank', 'noopener,noreferrer');
          }
        }}
      >
        <span className="client-contact-label">
          {t('client.instagram', 'Instagram')}
        </span>
        <span className="client-contact-arrow">↗</span>
      </button>
    )}

    {business.reviews_url && (
      <button
        type="button"
        className="client-contact-button"
        onClick={() => {
          if (tg()?.openLink) {
            tg().openLink(business.reviews_url);
          } else {
            window.open(business.reviews_url, '_blank', 'noopener,noreferrer');
          }
        }}
      >
        <span className="client-contact-label">
          {t('client.reviews', 'Отзывы')}
        </span>
        <span className="client-contact-arrow">↗</span>
      </button>
    )}

  </div>
  <button
    className={
      isSaved
        ? 'client-save-button saved'
        : 'client-save-button'
    }
    disabled={savingBusiness}
    onClick={toggleSave}
  >
    {isSaved
      ? t('client.savedBusiness')
      : t('client.saveBusiness')}
  </button>
        <div className="client-timezone-info">
          <p
            className="muted"
            style={{ marginTop: 10, marginBottom: 5, fontSize: 13 }}
          >
            {t('client.businessTimezone', 'Часовой пояс бизнеса')}: {business.timezone
              ? formatGMTOffset(getTimeZoneOffsetMinutes(business.timezone))
              : 'GMT+0'}
          </p>
          <p
            className="muted"
            style={{ marginBottom: 0, fontSize: 13 }}
          >
            {t(
              'client.slotsShownInYourTimezone',
              'Время свободных слотов отображается по вашему часовому поясу'
            )}: {formatGMTOffset(getTimeZoneOffsetMinutes(getClientTimeZone()))}
          </p>
        </div>
        <p
          className="muted"
          style={{ marginTop: 8, marginBottom: 0 }}
        >
          {specialists.length
            ? t('client.chooseSpecialistHint', 'Выберите специалиста ниже, чтобы продолжить.')
            : t('client.chooseServiceHint')}
        </p>

</div>

<details className="card client-my-bookings-card">
        <summary
          style={{
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 18
          }}
        >
          📅 {t('client.myBookings')}
        </summary>

        <div
          style={{
            marginTop: 15
          }}
        >
          <MyBookings t={t} />
        </div>
      </details>

      

      {specialists.length > 0 ? (
        <>
          <h2 className="client-step-title">{t('client.chooseSpecialist', 'Выберите специалиста')}</h2>
          {!selectedSpecialist ? (
            <div className="card client-specialist-list-card">
              <div className="client-specialist-list">
                {specialists.map((specialist) => (
                  <button type="button" key={specialist.id} className="client-specialist-row" onClick={() => chooseSpecialist(specialist)}>
                    {specialist.photo ? <img src={specialist.photo} alt={specialist.name} style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }} /> : <span style={{ width: 52, height: 52, borderRadius: '50%', background: '#f0f1f3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, flexShrink: 0 }}>{String(specialist.name || '?').charAt(0).toUpperCase()}</span>}
                    <span style={{ display: 'grid', gap: 2 }}><strong>{specialist.name}</strong>{specialist.position && <small style={{ opacity: 0.7 }}>{specialist.position}</small>}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="card client-selected-specialist-card">
                <div>
                  <span className="client-selected-specialist-label">
                    {t(
                      'client.selectedSpecialist',
                      'Выбран специалист'
                    )}
                  </span>
                  <strong>{selectedSpecialist.name}</strong>
                  {selectedSpecialist.position && (
                    <small>{selectedSpecialist.position}</small>
                  )}
                </div>

                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    setSelectedSpecialist(null);
                    setSelected(null);
                    setSelectedTime('');
                    setSlots([]);
                    setSlotItems([]);
                    setDay(
                      getClientLocalDateKey()
                    );
                  }}
                >
                  {t(
                    'client.change',
                    'Изменить'
                  )}
                </button>
              </div>
              <h2 id="client-services-step" className="client-step-title">{t('client.services')}</h2>
              {(() => {
                const specialistServices = selectedSpecialist.service_ids?.length ? services.filter((service: any) => selectedSpecialist.service_ids.includes(service.id)) : services;
                return specialistServices.length === 0 ? <div className="card"><p>{t('client.noServices')}</p></div> : specialistServices.map((service: any) => (
                  <div className={selected?.id === service.id ? 'client-service-card selected' : 'client-service-card'} key={service.id}>
                    <div className="client-service-info"><strong>{service.name}</strong><div className="client-service-meta">{money(service.price, service.currency)}<span>·</span>{service.duration_min} {t('owner.minutes')}</div>{service.description && <p>{service.description}</p>}</div>
                    <button className="client-service-button" onClick={() => chooseService(service)}>{t('client.chooseService')}</button>
                  </div>
                ));
              })()}
            </>
          )}
        </>
      ) : (
        <>
          <h2>{t('client.services')}</h2>
          {services.length === 0 ? <div className="card"><p>{t('client.noServices')}</p></div> : services.map((service: any) => (
            <div className={selected?.id === service.id ? 'client-service-card selected' : 'client-service-card'} key={service.id}>
              <div className="client-service-info"><strong>{service.name}</strong><div className="client-service-meta">{money(service.price, service.currency)}<span>·</span>{service.duration_min} {t('owner.minutes')}</div>{service.description && <p>{service.description}</p>}</div>
              <button className="client-service-button" onClick={() => chooseService(service)}>{t('client.chooseService')}</button>
            </div>
          ))}
        </>
      )}

      {selected && (
        <>
          <div
            id="client-schedule-step"
            className="card client-schedule-card"
          >
            <div className="client-schedule-head">
              <div>
                <span className="client-step-kicker">
                  {t(
                    'client.schedule',
                    'Расписание'
                  )}
                </span>
                <h2>
                  {t(
                    'client.chooseTime',
                    'Выберите время'
                  )}
                </h2>
              </div>

              <label className="client-date-control">
                <span>
                  {t(
                    'client.chooseDate',
                    'Дата'
                  )}
                </span>
                <input
                  type="date"
                  min={getClientLocalDateKey()}
                  value={day}
                  onChange={async e => {
                    const newDay =
                      e.target.value;
                    setDay(newDay);
                    setSelectedTime('');
                    await loadSlots(
                      selected,
                      newDay,
                      selectedSpecialist
                    );
                  }}
                />
              </label>
            </div>

            <div className="client-slot-legend">
              <span>
                <i className="available" />
                {t(
                  'client.available',
                  'Свободно'
                )}
              </span>
              <span>
                <i className="unavailable" />
                {t(
                  'client.unavailable',
                  'Занято'
                )}
              </span>
            </div>

            {slotsLoading ? (
              <p className="muted">
                {t(
                  'owner.loadingSlots',
                  'Загружаем свободное время...'
                )}
              </p>
            ) : slotItems.length > 0 ? (
              <div className="client-slot-calendar">
                {slotItems.map(slot => (
                  <button
                    type="button"
                    key={slot.time}
                    disabled={!slot.available}
                    className={
                      [
                        'client-slot-cell',
                        slot.available
                          ? 'available'
                          : 'unavailable',
                        selectedTime ===
                        slot.time
                          ? 'selected'
                          : ''
                      ]
                        .filter(Boolean)
                        .join(' ')
                    }
                    onClick={() => {
                      if (slot.available) {
                        chooseTime(slot.time);
                      }
                    }}
                  >
                    {slot.time}
                  </button>
                ))}
              </div>
            ) : (
              <p className="muted">
                {t(
                  'client.noSlots',
                  'На эту дату свободного времени нет.'
                )}
              </p>
            )}
          </div>

          {selectedTime && (
            <div
              id="booking-form"
              className="card client-booking-form-card"
            >
              <h2>{t('client.yourData')}</h2>
              <div className="success">
                <b>{selected.name}</b>
                <br />
                {selectedSpecialist?.name && (
                  <>
                    {selectedSpecialist.name}
                    <br />
                  </>
                )}
                {day} · {selectedTime}
              </div>

              <input
                type="text"
                placeholder={t('client.name')}
                value={clientName}
                onChange={e =>
                  setClientName(e.target.value)
                }
              />

              <PhoneInput
                value={phone}
                onChange={setPhone}
                placeholder={t('client.phone')}
              />

              <button
                className="primary full"
                disabled={bookingLoading}
                onClick={submitBooking}
              >
                {bookingLoading
                  ? t('client.bookingLoading')
                  : t('client.confirmBooking')}
              </button>
            </div>
          )}
        </>
      )}

      <a
        className="client-powered-by"
        href="https://skedwoo.vercel.app/landing.html"
        target="_blank"
        rel="noreferrer"
        aria-label={t(
          'client.createBookingPage',
          'Create your own booking page with Skedwoo'
        )}
      >
        <span>{t('client.poweredBy', 'Powered by')}</span>
        <strong>Skedwoo</strong>
        <span aria-hidden="true">↗</span>
      </a>

    </section>
  );
}
