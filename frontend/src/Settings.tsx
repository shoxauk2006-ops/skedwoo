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
import { MapPicker } from './MapPicker';

function normalizeInstagramUrl(value: string): string | null {
  const input = value.trim().replace(/^@/, '');
  if (!input) return '';

  const candidate = /^https?:\/\//i.test(input)
    ? input
    : /^(?:www\.)?instagram\.com\//i.test(input)
      ? `https://${input}`
      : `https://www.instagram.com/${input}`;

  try {
    const parsed = new URL(candidate);
    const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
    const username = parsed.pathname.split('/').filter(Boolean)[0] || '';
    if (
      !['instagram.com'].includes(host) ||
      !/^[a-zA-Z0-9._]{1,30}$/.test(username)
    ) return null;

    return `https://www.instagram.com/${username}/`;
  } catch {
    return null;
  }
}

function normalizeReviewsUrl(value: string): string | null {
  const input = value.trim();
  if (!input) return '';

  try {
    const parsed = new URL(input);
    if (!['https:', 'http:'].includes(parsed.protocol)) return null;
    parsed.protocol = 'https:';
    return parsed.toString();
  } catch {
    return null;
  }
}

export function Settings({
  business,
  reload,
  t
}: {
  business: any;
  reload: () => void;
  t: (key: string, fallback?: string) => string;
}) {
  const [name, setName] = useState(
    business?.name || ''
  );

  const [description, setDescription] =
    useState(
      business?.description || ''
    );

  const [mapPickerOpen, setMapPickerOpen] =
  useState(false);

  const [address, setAddress] =
    useState(
      business?.address || ''
    );

  const [phone, setPhone] =
    useState(
      business?.phone || ''
    );

  const [instagramUrl, setInstagramUrl] =
    useState(business?.instagram_url || '');

  const [reviewsUrl, setReviewsUrl] =
    useState(business?.reviews_url || '');

  const [latitude, setLatitude] =
    useState(
      business?.latitude ?? ''
    );

  const [longitude, setLongitude] =
    useState(
      business?.longitude ?? ''
    );

  const [settingsTimezone, setSettingsTimezone] =
  useState(
    business?.timezone ||
      Intl.DateTimeFormat()
        .resolvedOptions()
        .timeZone ||
      'Asia/Tashkent'
  );

  const [currentTimezoneTime, setCurrentTimezoneTime] =
  useState(new Date());

  useEffect(() => {
  const timer = setInterval(() => {
    setCurrentTimezoneTime(new Date());
  }, 1000);

  return () => {
    clearInterval(timer);
  };
}, []);
    
  const [businessImage, setBusinessImage] =
    useState(
      business?.business_image || ''
    );
  

  const [saving, setSaving] =
    useState(false);

  const [deletingBusiness, setDeletingBusiness] =
  useState(false);

  const [qrDataUrl, setQrDataUrl] =
    useState('');

  const clientLink =
    `https://t.me/${BOT_USERNAME}?startapp=${business.slug}`;

  useEffect(() => {
    const generateQR = async () => {
      try {
        const url =
          await QRCode.toDataURL(
            clientLink,
            {
              width: 500,
              margin: 3,
              errorCorrectionLevel: 'H'
            }
          );

        setQrDataUrl(url);
      } catch (e) {
        console.error(
          'QR ERROR:',
          e
        );
      }
    };

    generateQR();
  }, [clientLink]);

  useEffect(() => {
  setName(
    business?.name || ''
  );

  setDescription(
    business?.description || ''
  );

  setAddress(
    business?.address || ''
  );

  setPhone(
    business?.phone || ''
  );

  setInstagramUrl(
    business?.instagram_url || ''
  );

  setReviewsUrl(
    business?.reviews_url || ''
  );

  setLatitude(
    business?.latitude ?? ''
  );

  setLongitude(
  business?.longitude ?? ''
);

    setSettingsTimezone(
  business?.timezone ||
    Intl.DateTimeFormat()
      .resolvedOptions()
      .timeZone ||
    'Asia/Tashkent'
);
}, [business]);
  
    const handleBusinessImage = (
    file?: File
  ) => {
    if (!file) {
      return;
    }

    if (!file.type.startsWith('image/')) {
      alert(
        t(
          'settings.invalidImage',
          'Выберите изображение'
        )
      );
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      alert(
        t(
          'settings.imageTooLarge',
          'Размер изображения не должен превышать 5 МБ'
        )
      );
      return;
    }

    const objectUrl =
      URL.createObjectURL(file);

    const image =
      new Image();

    image.onload = () => {
      const maxWidth = 1200;
      const maxHeight = 800;

      const scale = Math.min(
        maxWidth / image.width,
        maxHeight / image.height,
        1
      );

      const canvas =
        document.createElement('canvas');

      canvas.width =
        Math.round(
          image.width * scale
        );

      canvas.height =
        Math.round(
          image.height * scale
        );

      const ctx =
        canvas.getContext('2d');

      if (!ctx) {
        URL.revokeObjectURL(
          objectUrl
        );
        return;
      }

      ctx.drawImage(
        image,
        0,
        0,
        canvas.width,
        canvas.height
      );

      const compressed =
        canvas.toDataURL(
          'image/jpeg',
          0.82
        );

      setBusinessImage(
        compressed
      );

      URL.revokeObjectURL(
        objectUrl
      );
    };

    image.src =
      objectUrl;
  };
  const save = async () => {
        
    if (!phone.trim()) {
  alert(
    t(
      'owner.enterBusinessPhone',
      'Введите номер телефона бизнеса'
    )
  );
  return;
}

if (!isPhoneValid(phone)) {
  alert(
    t(
      'owner.invalidPhone',
      'Введите корректный номер телефона'
    )
  );
  return;
}

const normalizedInstagramUrl = normalizeInstagramUrl(instagramUrl);
if (normalizedInstagramUrl === null) {
  alert(t('settings.instagramInvalid', 'Введите имя пользователя Instagram или корректную ссылку на профиль.'));
  return;
}

const normalizedReviewsUrl = normalizeReviewsUrl(reviewsUrl);
if (normalizedReviewsUrl === null) {
  alert(t('settings.reviewsInvalid', 'Вставьте корректную ссылку на страницу с отзывами.'));
  return;
}

    setSaving(true);

    try {
      const response =
        await fetch(
          API + '/admin/business',
          {
            method: 'PUT',
            headers: headers(),
            body: JSON.stringify({
  name: name.trim(),
  business_image:
    businessImage || '',
  description:
    description.trim(),
  address:
    address.trim(),
  phone:
    phone.trim(),
  instagram_url: normalizedInstagramUrl,
  reviews_url: normalizedReviewsUrl,
  latitude:
    latitude === ''
      ? null
      : Number(latitude),
  longitude:
    longitude === ''
      ? null
      : Number(longitude),
              
    timezone: settingsTimezone,
})
          }
        );

      const data =
        await response
          .json()
          .catch(() => null);

      if (!response.ok) {
        throw new Error(
          data?.detail ||
          t(
            'owner.saveContactsError'
          )
        );
      }

      alert(
        t(
          'owner.contactsSaved'
        )
      );

      reload();

    } catch (e: any) {
      alert(
        e?.message ||
        t(
          'owner.saveContactsError'
        )
      );
    } finally {
      setSaving(false);
    }
  };
  const downloadQr = async () => {
  if (!qrDataUrl) {
    return;
  }

  try {
    const response =
      await fetch(qrDataUrl);

    const blob =
      await response.blob();

    const url =
      URL.createObjectURL(blob);

    const link =
      document.createElement('a');

    link.href = url;
    link.download =
      `${business.slug}-bookly-qr.png`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => {
      URL.revokeObjectURL(url);
    }, 1000);
  } catch (e) {
    console.error(
      'QR DOWNLOAD ERROR:',
      e
    );
  }
};

  
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(
        clientLink
      );

      alert(
        t(
          'settings.copyLink'
        )
      );
    } catch {
      alert(clientLink);
    }
  };

  const shareTelegram = () => {
    const shareUrl =
      `https://t.me/share/url?url=${encodeURIComponent(
        clientLink
      )}&text=${encodeURIComponent(
        business.name
      )}`;

    if (tg()?.openTelegramLink) {
      tg().openTelegramLink(
        shareUrl
      );
    } else {
      window.open(
        shareUrl,
        '_blank'
      );
    }
  };

  const downloadQR = () => {
    if (!qrDataUrl) {
      return;
    }

    const link =
      document.createElement('a');

    link.href = qrDataUrl;

    link.download =
      `${business.slug}-bookly-qr.png`;

    link.click();
  };
const deleteBusiness = async () => {
  const confirmed = await confirmAsync(
  t(
    'owner.deleteBusinessConfirm',
    'Вы действительно хотите удалить этот бизнес?\n\n' +
      'Все данные бизнеса, включая услуги, график работы, блокировки и записи, будут удалены без возможности восстановления.\n\n' +
      'Подписка при этом НЕ отменяется. Вы сможете создать новый бизнес и продолжить пользоваться активной подпиской.'
  )
);

    if (!confirmed) {
      return;
    }

    setDeletingBusiness(true);

    try {
      const response = await fetch(
        API + `/admin/business/${business.id}`,
        {
          method: 'DELETE',
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
t(
  'owner.deleteBusinessError',
  'Не удалось удалить бизнес'
)
        );
      }

      alert(
  t(
    'owner.businessDeleted',
    'Бизнес успешно удалён.'
  )
);

      reload();

        } catch (e: any) {
      alert(
        e?.message ||
t(
  'owner.deleteBusinessError',
  'Не удалось удалить бизнес'
)
      );
    } finally {
      setDeletingBusiness(false);
    }
  };
  return (
    <div>

      <div className="card">
        <h2>
          {t(
            'settings.businessInfo'
          )}
        </h2>
        <div className="business-photo-settings">
  <strong>
  {t(
    'owner.businessPhoto',
    'Фото бизнеса'
  )}
</strong>

  <p className="muted">
  {t(
    'owner.businessPhotoHint',
    'Добавьте фотографию, которая будет отображаться у клиентов.'
  )}
</p>

  {businessImage ? (
    <img
      src={businessImage}
      className="business-photo-preview"
      alt="Business"
      className="bookly-business-avatar"
    />
  ) : (
    <div className="business-photo-empty">
      Фото пока не добавлено
    </div>
  )}

  <div className="business-photo-actions">

  <label className="admin-action-button">
  {businessImage
    ? 'Заменить фото'
    : 'Добавить фото'}

  <input
    type="file"
    accept="image/*"
    hidden
    onChange={(e) => {
      const file =
        e.target.files?.[0];

      if (file) {
        handleBusinessImage(file);
      }

      e.target.value = '';
    }}
  />
</label>

  

  {businessImage && (
    <button
      type="button"
      className="ghost"
      onClick={() => {
        setBusinessImage('');
      }}
    >
      {t('common.delete')}
    </button>
  )}

</div>
</div>

        <input
          placeholder={t(
            'owner.serviceName'
          )}
          value={name}
          onChange={e =>
            setName(
              e.target.value
            )
          }
        />

        <textarea
          placeholder={t(
            'settings.description'
          )}
          value={description}
          onChange={e =>
            setDescription(
              e.target.value
            )
          }
        />

        <PhoneInput
  value={phone}
  onChange={setPhone}
  placeholder={t(
    'settings.phone'
  )}
/>

        <input
          placeholder={t(
            'settings.address'
          )}
          value={address}
          onChange={e =>
            setAddress(
              e.target.value
            )
          }
        />

        <div className="business-social-settings">
          <h3>{t('settings.socialLinks', 'Соцсети и отзывы')}</h3>
          <label htmlFor="business-instagram-url">
            {t('settings.instagram', 'Instagram')}
          </label>
          <input
            id="business-instagram-url"
            type="text"
            autoCapitalize="none"
            autoCorrect="off"
            placeholder="@username"
            value={instagramUrl}
            onChange={e => setInstagramUrl(e.target.value)}
          />
          <p className="muted">
            {t('settings.instagramHint', 'Укажите имя аккаунта или ссылку на профиль.')}
          </p>

          <label htmlFor="business-reviews-url">
            {t('settings.reviewsLink', 'Ссылка на отзывы')}
          </label>
          <input
            id="business-reviews-url"
            type="url"
            inputMode="url"
            autoCapitalize="none"
            autoCorrect="off"
            placeholder="https://..."
            value={reviewsUrl}
            onChange={e => setReviewsUrl(e.target.value)}
          />
          <p className="muted">
            {t('settings.reviewsHint', 'Добавьте ссылку на отзывы в Google Maps, 2GIS или другом сервисе.')}
          </p>
        </div>
        
        <button
  type="button"
  className="ghost full"
  onClick={() =>
    setMapPickerOpen(true)
  }
>
  {latitude !== '' &&
  longitude !== ''
    ? t(
        'owner.changeMapPoint',
        'Изменить точку на карте'
      )
    : t(
        'owner.chooseMapLocation',
        'Выбрать адрес на карте'
      )}
</button>

{latitude !== '' &&
  longitude !== '' && (
    <p className="muted">
      {Number(latitude).toFixed(
        6
      )}
      ,{' '}
      {Number(longitude).toFixed(
        6
      )}
    </p>
  )}

{mapPickerOpen && (
  <MapPicker
    latitude={
      latitude === ''
        ? null
        : Number(latitude)
    }
    longitude={
      longitude === ''
        ? null
        : Number(longitude)
    }
    onSelect={(
      lat,
      lng,
      selectedAddress
    ) => {
      setLatitude(
        String(lat)
      );

      setLongitude(
        String(lng)
      );

      if (selectedAddress) {
        setAddress(
          selectedAddress
        );
      }
    }}
    onClose={() =>
      setMapPickerOpen(false)
    }
    t={t}
  />
)}

        <div
  style={{
    marginTop: 14
  }}
>
  <label
    style={{
      display: 'block',
      marginBottom: 8,
      fontWeight: 600
    }}
  >
    {t(
      'owner.businessTimezone',
      'Часовой пояс'
    )}
  </label>

  <div
    style={{
      padding: '13px 14px',
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      background: '#f8f9fa'
    }}
  >
    <div
      style={{
        fontWeight: 600
      }}
    >
      {getTimeZoneLabel(
        settingsTimezone
      )}
    </div>

    <div
      style={{
        marginTop: 4,
        color: '#707780',
        fontSize: 14
      }}
    >
      {new Intl.DateTimeFormat(
        undefined,
        {
          timeZone: settingsTimezone,
          timeZoneName: 'shortOffset',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false
        }
      ).format(currentTimezoneTime)}
    </div>
  </div>
</div>

                <button
          className="primary full"
          disabled={saving}
          onClick={save}
        >
          {saving
            ? t('owner.saving')
            : t('common.save')}
        </button>

        <div
          style={{
            marginTop: '24px',
            paddingTop: '20px',
            borderTop: '1px solid rgba(0,0,0,0.08)'
          }}
        >
          <button
  type="button"
  className="ghost full"
  disabled={deletingBusiness}
  onClick={deleteBusiness}
  style={{
    color: '#d32f2f',
    borderColor: '#d32f2f'
  }}
>
  {deletingBusiness ? (
    <>
      <span
        style={{
          display: 'inline-block',
          width: 14,
          height: 14,
          border: '2px solid rgba(211,47,47,0.25)',
          borderTopColor: '#d32f2f',
          borderRadius: '50%',
          animation: 'bookly-spin .8s linear infinite',
          marginRight: 8,
          verticalAlign: '-2px'
        }}
      />
      {t(
  'owner.deleting',
  'Удаление...'
)}
    </>
  ) : (
    t(
  'owner.deleteBusiness',
  'Удалить бизнес'
)
  )}
</button>
        </div>

      </div>
    </div>
  );
}
