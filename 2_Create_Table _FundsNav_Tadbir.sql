
CREATE TABLE [DBO].[FundsNAV_Tadibr](
	[funddate_key] [nvarchar](100) NULL,
	[DScode] [nvarchar](100) NULL,
	[jdatekey] [bigint] NULL,
	[JalaliDate] [nvarchar](100) NULL,
	[FundName] [nvarchar](400) NULL,
	[BasketId] [int] NULL,
	[SubscriptionNAV] [bigint] NULL,
	[TotalNetAssetValue] [bigint] NULL,
	[CancelNAV] [bigint] NULL,
	[EsmiNAV] [bigint] NULL,
	[NavDiff] [bigint] NULL,
	[TotalSubscriptionUnit] [bigint] NULL,
	[TotalSubscription] [bigint] NULL,
	[TotalCancel] [bigint] NULL,
	[TotalCancelUnit] [bigint] NULL,
	[TotalUnit] [bigint] NULL,
	[Date] [nvarchar](50) NULL,
	[StockValueReserve] [bigint] NULL
) ON [PRIMARY]
GO

