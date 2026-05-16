CREATE TABLE [DBO].[FundsNav_NavUrls](
  [Dscode]              NVARCHAR(50) NULL,
  [fundName]            NVARCHAR(200) NULL,
  [fundtype]            NVARCHAR(50) NULL,
  [Investment_Type]     NVARCHAR(50) NULL,
  [website_Type]        NVARCHAR(50) NULL,
  [Website_main_url]    NVARCHAR(MAX) NULL,
  [NAV_URL]             NVARCHAR(MAX) NULL)
  [Manager]        		NVARCHAR(200) NULL
ON [PRIMARY]
TEXTIMAGE_ON [PRIMARY]
WITH(DATA_COMPRESSION = NONE);
GO

